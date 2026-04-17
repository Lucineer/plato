#!/usr/bin/env python3
"""
PLATO Tile Maker — Local LLM Tile Generation

Uses llama.cpp with local models to generate high-quality tiles from
raw content. Slow but permanent — each tile improves the system forever.

Design:
  - Load a local GGUF model via llama-cpp-python
  - Feed raw markdown content in chunks
  - Ask the model to extract teachable Q&A pairs
  - Validate against existing tiles
  - Stage for review (or auto-merge if confidence > threshold)

Resource budget:
  - phi-4 (3.8B): ~3.5GB VRAM, ~15 tok/s on Jetson
  - Qwen3-32B Q4: ~20GB (won't fit on 8GB Jetson)
  - DeepSeek-R1 Q4: ~34GB (won't fit)
  - Best fit: phi-4 or smaller Qwen2.5-7B Q4 (~4.5GB)
  
Even at 15 tok/s, a 200-token tile takes ~13 seconds.
That's ~4 tiles/minute = ~240 tiles/hour on spare compute.
Each tile is permanent. 240 tiles/hour × 8 hours overnight = 1,920 tiles/day.

Usage:
  python3 tile_maker.py --model /path/to/model.gguf --content /path/to/dir
  python3 tile_maker.py --room flux_runtime --content /tmp/oracle1-vessel/KNOWLEDGE
  python3 tile_maker.py --list-models
"""

import json
import os
import re
import sys
import time
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ─── Config ──────────────────────────────────────────────────────────

PLATO_DEPLOY = os.environ.get("PLATO_DEPLOY",
    "/home/lucineer/.openclaw/workspace/plato-deploy")
TILES_DIR = os.path.join(PLATO_DEPLOY, "data", "tiles")
STAGING_DIR = "/tmp/jetsonclaw1/tile-forge/staging"
LOG_FILE = "/tmp/jetsonclaw1/tile-forge/maker.log"

# Recommended models for Jetson Orin (8GB unified)
RECOMMENDED_MODELS = {
    "phi-4": {
        "url": "https://huggingface.co/microsoft/phi-4/resolve/main/phi-4-q4.gguf",
        "size_gb": 2.2,
        "tok_per_sec": "~15",
        "quality": "good",
        "fits_jetson": True,
    },
    "Qwen2.5-7B-Instruct-Q4": {
        "url": "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf",
        "size_gb": 4.5,
        "tok_per_sec": "~8",
        "quality": "very good",
        "fits_jetson": True,
    },
    "Qwen2.5-3B-Instruct-Q4": {
        "url": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
        "size_gb": 2.0,
        "tok_per_sec": "~25",
        "quality": "decent",
        "fits_jetson": True,
    },
}

# Tile generation prompt — the key instruction
TILE_MAKER_PROMPT = """You are a knowledge tile maker for a PLATO room. Your job is to extract teachable Q&A pairs from the content below.

For each useful piece of knowledge, create a tile:
- **Question**: What someone would ASK to learn this
- **Answer**: A complete, self-contained explanation (2-4 sentences)

Rules:
- Extract ONLY knowledge that would help someone actually DO something or UNDERSTAND something
- Skip: metadata, file paths, placeholder text, TODOs, formatting notes
- Skip: duplicate information (only extract each fact once)
- Include: technical details, commands, configurations, constraints, procedures
- Make questions natural — "How do I..." or "What is..." or "Why does..."
- Make answers self-contained — don't reference "above" or "this section"
- If the content has [WordAnchors] like [Term], preserve them in the answer
- Maximum 5 tiles per chunk. Quality over quantity.

Output format (strict JSON):
```json
[
  {"question": "...", "answer": "...", "tags": ["tag1", "tag2"]},
  ...
]
```

If no useful tiles can be extracted, output: ```json\n[]\n```

Content to extract from:
"""


def log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ─── LLM Tile Generator ─────────────────────────────────────────────

class LocalTileMaker:
    """Generate tiles using a local GGUF model via llama-cpp-python."""
    
    def __init__(self, model_path: str, n_ctx: int = 2048, n_gpu_layers: int = -1):
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self.llm = None
        self._loaded = False
    
    def load(self):
        """Load the model into memory."""
        if self._loaded:
            return
        
        log(f"Loading model: {self.model_path}")
        from llama_cpp import Llama
        
        # Start with CPU-only to test, then try GPU
        try:
            self.llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_gpu_layers=self.n_gpu_layers,  # -1 = all layers to GPU
                verbose=False,
                n_threads=4,  # Leave 2 cores for system
            )
            log(f"Model loaded (GPU layers: {self.n_gpu_layers})")
        except Exception as e:
            log(f"GPU load failed ({e}), trying CPU...")
            self.llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_gpu_layers=0,  # CPU only
                verbose=False,
                n_threads=4,
            )
            log(f"Model loaded (CPU only)")
        
        self._loaded = True
    
    def unload(self):
        """Free model memory."""
        if self.llm:
            del self.llm
            self.llm = None
            self._loaded = False
            import gc
            gc.collect()
            log("Model unloaded, memory freed")
    
    def generate_tiles(self, content: str, room_context: str = "") -> List[dict]:
        """Generate tiles from content using the local model."""
        if not self._loaded:
            self.load()
        
        # Chunk content if too long (rough estimate: 1 char ≈ 0.25 tokens)
        max_chars = self.n_ctx * 3  # Leave room for prompt + output
        chunks = self._chunk_content(content, max_chars)
        
        all_tiles = []
        for i, chunk in enumerate(chunks):
            log(f"  Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
            
            prompt = TILE_MAKER_PROMPT
            if room_context:
                prompt += f"\nRoom context: {room_context}\n\n"
            prompt += chunk
            
            try:
                response = self.llm(
                    prompt,
                    max_tokens=1024,
                    temperature=0.3,
                    stop=["```", "\n\n\n"],
                    echo=False,
                )
                text = response["choices"][0]["text"].strip()
                tiles = self._parse_tiles(text)
                all_tiles.extend(tiles)
                log(f"    → {len(tiles)} tiles extracted")
            except Exception as e:
                log(f"    → Error: {e}")
        
        return all_tiles
    
    def _chunk_content(self, content: str, max_chars: int) -> List[str]:
        """Split content into chunks at natural boundaries."""
        if len(content) <= max_chars:
            return [content]
        
        chunks = []
        lines = content.split('\n')
        current = []
        current_len = 0
        
        for line in lines:
            line_len = len(line) + 1
            if current_len + line_len > max_chars and current:
                chunks.append('\n'.join(current))
                current = []
                current_len = 0
            current.append(line)
            current_len += line_len
        
        if current:
            chunks.append('\n'.join(current))
        
        return chunks
    
    def _parse_tiles(self, text: str) -> List[dict]:
        """Parse JSON tile output from model."""
        tiles = []
        
        # Try to find JSON array in output
        # Models sometimes wrap in ```json ... ```
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if not json_match:
            return tiles
        
        try:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and "question" in item and "answer" in item:
                        q = item["question"].strip()
                        a = item["answer"].strip()
                        if len(q) > 10 and len(a) > 20:
                            tiles.append({
                                "question": q,
                                "answer": a,
                                "tags": item.get("tags", ["llm-generated"]),
                                "source": "forge:llm-local",
                                "confidence": 0.7,  # LLM tiles get higher base confidence
                                "extraction_type": "llm-synthesis",
                            })
        except json.JSONDecodeError:
            log(f"    JSON parse failed: {text[:100]}...")
        
        return tiles


# ─── Tile Validator (shared with tile_forge.py) ─────────────────────

def load_room_tiles(room_id: str) -> List[dict]:
    room_file = os.path.join(TILES_DIR, f"{room_id}.json")
    if os.path.exists(room_file):
        try:
            with open(room_file) as f:
                return json.load(f)
        except:
            pass
    return []


def validate_tile(tile: dict, existing: List[dict]) -> Tuple[bool, str]:
    existing_norms = {re.sub(r'[^\w\s]', '', t.get("question", "").lower()) for t in existing}
    
    q_norm = re.sub(r'[^\w\s]', '', tile["question"].lower())
    if q_norm in existing_norms:
        return False, "duplicate"
    if len(tile["question"]) < 10:
        return False, "question too short"
    if len(tile["answer"]) < 20:
        return False, "answer too short"
    if len(tile["answer"].split()) < 5:
        return False, "too few words"
    est_tokens = (len(tile["question"]) + len(tile["answer"])) // 4
    if est_tokens > 250:
        return False, f"too large ({est_tokens} tokens)"
    
    return True, "valid"


def stage_tiles(room_id: str, tiles: List[dict]) -> int:
    existing = load_room_tiles(room_id)
    valid = []
    for t in tiles:
        ok, reason = validate_tile(t, existing)
        if ok:
            valid.append({
                "question": t["question"],
                "answer": t["answer"],
                "source": t.get("source", "forge:llm-local"),
                "tags": t.get("tags", ["llm-generated"]),
                "feedback_positive": 0,
                "feedback_negative": 0,
                "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
        else:
            log(f"  Rejected: {t['question'][:40]}... ({reason})")
    
    if not valid:
        return 0
    
    os.makedirs(STAGING_DIR, exist_ok=True)
    stage_file = os.path.join(STAGING_DIR, f"{room_id}-llm-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with open(stage_file, "w") as f:
        json.dump(valid, f, indent=2)
    log(f"  Staged {len(valid)} LLM tiles → {stage_file}")
    return len(valid)


# ─── Content Discovery ──────────────────────────────────────────────

def discover_content(content_path: str) -> List[str]:
    """Find markdown files to process."""
    files = []
    path = Path(content_path)
    if path.is_file() and path.suffix in ('.md', '.txt', '.rst'):
        files.append(str(path))
    elif path.is_dir():
        for p in path.rglob('*'):
            if p.is_file() and p.suffix in ('.md', '.txt', '.rst'):
                if '.git' not in str(p):
                    files.append(str(p))
    return sorted(files)


# ─── Room Context Builder ───────────────────────────────────────────

def get_room_context(room_id: str) -> str:
    """Build a brief description of the room for the LLM."""
    tiles = load_room_tiles(room_id)
    if not tiles:
        return f"Room: {room_id} (new room, no existing tiles)"
    
    # Sample existing tiles to give the LLM context about what's already covered
    sample = tiles[:5]
    existing_q = [f"- {t['question']}" for t in sample]
    return f"""Room: {room_id}
Existing tiles ({len(tiles)} total, sample):
{chr(10).join(existing_q)}
Generate tiles that COMPLEMENT but don't DUPLICATE these."""


# ─── Main ───────────────────────────────────────────────────────────

def run_maker(model_path: str, content_path: str, room_id: str,
              dry_run: bool = True, max_files: int = 10, max_time: int = 600):
    """Main tile making loop."""
    log("=" * 60)
    log(f"PLATO Tile Maker — local LLM mode")
    log(f"  model: {model_path}")
    log(f"  room: {room_id}")
    log(f"  content: {content_path}")
    log(f"  dry_run: {dry_run}, max_files: {max_files}")
    
    # Check model exists
    if not os.path.exists(model_path):
        log(f"ERROR: Model not found at {model_path}")
        log(f"Recommended models for Jetson (8GB):")
        for name, info in RECOMMENDED_MODELS.items():
            fits = "✅" if info["fits_jetson"] else "❌"
            log(f"  {fits} {name}: {info['size_gb']}GB, ~{info['tok_per_sec']} tok/s, quality: {info['quality']}")
        return 0
    
    # Discover content
    files = discover_content(content_path)
    if not files:
        log(f"ERROR: No markdown files found at {content_path}")
        return 0
    
    files = files[:max_files]
    log(f"  Found {len(files)} files to process")
    
    # Load model
    maker = LocalTileMaker(model_path, n_ctx=2048, n_gpu_layers=-1)
    maker.load()
    
    start = time.time()
    total_tiles = 0
    
    room_context = get_room_context(room_id)
    
    for i, fp in enumerate(files):
        if time.time() - start > max_time:
            log(f"  Time limit reached ({max_time}s)")
            break
        
        log(f"\n  [{i+1}/{len(files)}] {os.path.basename(fp)}")
        try:
            with open(fp) as f:
                content = f.read()
            
            if len(content) < 50:
                log(f"    → too short, skipping")
                continue
            
            tiles = maker.generate_tiles(content, room_context)
            staged = stage_tiles(room_id, tiles)
            total_tiles += staged
            
        except Exception as e:
            log(f"    → Error: {e}")
    
    # Free memory
    maker.unload()
    
    elapsed = time.time() - start
    log(f"\n{'=' * 60}")
    log(f"Tile Maker complete: {total_tiles} tiles in {elapsed:.0f}s")
    log(f"  Files processed: {len(files)}")
    log(f"  Rate: {total_tiles/(elapsed/60):.1f} tiles/minute")
    
    return total_tiles


def list_models():
    """List available and recommended models."""
    print("Recommended models for Jetson Orin (8GB unified):")
    print()
    for name, info in RECOMMENDED_MODELS.items():
        fits = "✅ FITS" if info["fits_jetson"] else "❌ TOO LARGE"
        print(f"  {fits} | {name}")
        print(f"       Size: {info['size_gb']}GB")
        print(f"       Speed: {info['tok_per_sec']} tokens/sec")
        print(f"       Quality: {info['quality']}")
        print(f"       URL: {info['url']}")
        print()
    
    # Check for locally downloaded models
    print("Locally downloaded models:")
    model_dirs = [
        "/home/lucineer/.ollama/models",
        "/home/lucineer/.cache/huggingface/hub",
        "/home/lucineer/models",
    ]
    found = False
    for d in model_dirs:
        if os.path.exists(d):
            for root, dirs, files in os.walk(d):
                for f in files:
                    if f.endswith('.gguf'):
                        size_gb = os.path.getsize(os.path.join(root, f)) / (1024**3)
                        print(f"  ✅ {os.path.join(root, f)} ({size_gb:.1f}GB)")
                        found = True
    if not found:
        print("  No GGUF models found locally.")
        print(f"  Download one with:")
        print(f"    cd /home/lucineer/models")
        print(f"    wget {RECOMMENDED_MODELS['Qwen2.5-3B-Instruct-Q4']['url']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PLATO Tile Maker — Local LLM")
    parser.add_argument("--model", type=str, help="Path to GGUF model file")
    parser.add_argument("--content", type=str, help="Path to content dir/file to process")
    parser.add_argument("--room", type=str, required=True, help="Target room ID")
    parser.add_argument("--live", action="store_true", help="Actually merge (not dry-run)")
    parser.add_argument("--files", type=int, default=10, help="Max files to process")
    parser.add_argument("--time", type=int, default=600, help="Max time in seconds")
    parser.add_argument("--list-models", action="store_true", help="List recommended models")
    parser.add_argument("--download-phi4", action="store_true", help="Download phi-4 Q4 model")
    args = parser.parse_args()
    
    if args.list_models:
        list_models()
        sys.exit(0)
    
    if args.download_phi4:
        import urllib.request
        model_dir = "/home/lucineer/models"
        os.makedirs(model_dir, exist_ok=True)
        url = RECOMMENDED_MODELS["phi-4"]["url"]
        dest = os.path.join(model_dir, "phi-4-q4.gguf")
        log(f"Downloading phi-4 to {dest}...")
        urllib.request.urlretrieve(url, dest)
        log(f"Downloaded: {os.path.getsize(dest)/(1024**3):.1f}GB")
        sys.exit(0)
    
    if not args.model or not args.content:
        parser.print_help()
        print("\nQuick start:")
        print("  python3 tile_maker.py --list-models")
        print("  python3 tile_maker.py --room flux_runtime --content /tmp/oracle1-vessel/KNOWLEDGE --model /home/lucineer/models/phi-4-q4.gguf")
        sys.exit(1)
    
    run_maker(args.model, args.content, args.room,
              dry_run=not args.live, max_files=args.files, max_time=args.time)
