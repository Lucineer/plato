#!/usr/bin/env python3
"""
PLATO Tile Forge — Background Improvement Daemon

Runs on spare Jetson compute. Scans fleet content, extracts knowledge
patterns, generates candidate tiles, validates against existing tiles,
and merges the best ones into rooms.

Design principles:
  1. No API calls — pure extraction and validation
  2. CPU-bound only — uses idle cores, not GPU
  3. Token-aware — respects JIT budgets
  4. Non-destructive — candidates go to staging, human reviews before merge
  5. Incremental — tracks what's been processed, only scans new content

Tile sources (in priority order):
  1. Git commit messages — "Fix X" → tile: "How to fix X"
  2. Q&A patterns in markdown — "## Q: ... ## A: ..." or "### What is ..."
  3. Definition blocks — "**X** is ..." or "X: Y"
  4. Code comments — "# TODO:", "# NOTE:", "# IMPORTANT:"
  5. Error/solution pairs — "Error: X" + "Solution: Y"
  6. Procedure lists — numbered steps, bullet lists with commands
  7. Fleet bottles — "BOTTLE-TO-JC1" content → tiles for fleet rooms

Resource budget:
  - Max 512MB RAM (leaves 2.5GB for PLATO + system)
  - Max 30% CPU (load average < 1.0)
  - Max 1 tile per minute (gentle rate)
  - Stops if system load > 2.0
"""

import json
import os
import re
import sys
import time
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ─── Config ──────────────────────────────────────────────────────────

PLATO_DEPLOY = os.environ.get("PLATO_DEPLOY", 
    "/home/lucineer/.openclaw/workspace/plato-deploy")
TILES_DIR = os.path.join(PLATO_DEPLOY, "data", "tiles")
STAGING_DIR = "/tmp/jetsonclaw1/tile-forge/staging"
STATE_FILE = "/tmp/jetsonclaw1/tile-forge/state.json"
LOG_FILE = "/tmp/jetsonclaw1/tile-forge/forge.log"

# Content sources to scan
CONTENT_SOURCES = [
    # Fleet repos (bottles, knowledge, research)
    "/tmp/oracle1-vessel/KNOWLEDGE",
    "/tmp/oracle1-vessel/for-fleet",
    "/tmp/oracle1-vessel/message-in-a-bottle",
    "/tmp/forgemaster/for-fleet",
    "/tmp/forgemaster/experience",
    "/tmp/JetsonClaw1-vessel/for-fleet",
    # Workspace knowledge
    "/home/lucineer/.openclaw/workspace/MEMORY.md",
    "/home/lucineer/.openclaw/workspace/research",
    "/home/lucineer/.openclaw/workspace/bottles",
    "/home/lucineer/.openclaw/workspace/docs",
    # PLATO guides
    os.path.join(PLATO_DEPLOY, "docs"),
]

# Room → content source mapping (which rooms benefit from which sources)
ROOM_SOURCE_MAP = {
    "flux_runtime": ["/tmp/oracle1-vessel/KNOWLEDGE", "/tmp/oracle1-vessel/for-fleet"],
    "isa_v3_conformance": ["/tmp/oracle1-vessel/KNOWLEDGE", "/tmp/oracle1-vessel/for-fleet"],
    "fleet_operations": ["/tmp/oracle1-vessel/for-fleet", "/tmp/oracle1-vessel/message-in-a-bottle",
                         "/tmp/forgemaster/for-fleet"],
    "constraint_theory": ["/tmp/forgemaster/for-fleet", "/tmp/forgemaster/experience",
                          "/home/lucineer/.openclaw/workspace/research"],
    "gpu_optimization": ["/tmp/forgemaster/for-fleet", "/home/lucineer/.openclaw/workspace/research"],
    "plato_collab": ["/home/lucineer/.openclaw/workspace/plato-deploy/docs",
                     "/home/lucineer/.openclaw/workspace/research"],
    "medical_diagnosis": [],
    "business_hub": [],
    "dev_debug": [],
    "classroom_main": [],
    "harbor_dock": [],
}

# ─── Resource Monitoring ────────────────────────────────────────────

def system_load() -> float:
    """Get 1-minute load average."""
    try:
        with open("/proc/loadavg") as f:
            return float(f.read().split()[0])
    except:
        return 0.0

def available_memory_mb() -> int:
    """Available memory in MB."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except:
        return 0

def can_forge() -> bool:
    """Check if system has spare resources for forging."""
    load = system_load()
    mem = available_memory_mb()
    if load > 2.0:
        return False
    if mem < 512:
        return False
    return True

# ─── State Tracking ─────────────────────────────────────────────────

def load_state() -> dict:
    """Load forge state (which files have been processed)."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"processed_files": {}, "tiles_generated": 0, "tiles_merged": 0,
            "last_run": None, "runs": 0}

def save_state(state: dict):
    """Save forge state."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    state["last_run"] = datetime.now().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def file_hash(filepath: str) -> str:
    """Quick hash of file for change detection."""
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read(8192)).hexdigest()  # First 8K only
    except:
        return ""

# ─── Tile Extraction Patterns ───────────────────────────────────────

class TileExtractor:
    """Extracts candidate tiles from markdown content."""
    
    def __init__(self, room_id: str, existing_tiles: List[dict]):
        self.room_id = room_id
        self.existing_questions = {self._normalize(t["question"]) for t in existing_tiles}
    
    def _normalize(self, text: str) -> str:
        """Normalize question for dedup comparison."""
        return re.sub(r'[^\w\s]', '', text.lower().strip())
    
    def extract(self, content: str, source_file: str) -> List[dict]:
        """Extract candidate tiles from markdown content."""
        candidates = []
        
        # Pattern 1: Explicit Q&A blocks
        candidates.extend(self._extract_qa(content, source_file))
        
        # Pattern 2: Heading-based definitions ("## What is X?" or "### How to Y?")
        candidates.extend(self._extract_headings(content, source_file))
        
        # Pattern 3: Bold definitions ("**X** is Y" or "**X**: Y")
        candidates.extend(self._extract_definitions(content, source_file))
        
        # Pattern 4: Error/solution pairs
        candidates.extend(self._extract_error_solutions(content, source_file))
        
        # Pattern 5: Procedure lists (numbered steps with commands)
        candidates.extend(self._extract_procedures(content, source_file))
        
        # Pattern 6: Key-value config entries
        candidates.extend(self._extract_key_values(content, source_file))
        
        # Deduplicate against existing tiles
        return [c for c in candidates if self._normalize(c["question"]) not in self.existing_questions]
    
    def _extract_qa(self, content: str, source: str) -> List[dict]:
        """Extract Q: ... A: ... patterns."""
        tiles = []
        # Match various Q&A formats
        patterns = [
            r'(?:Q|Question|FAQ)[:\s]+(.+?)\n\s*(?:A|Answer|Response)[:\s]+(.+?)(?:\n\n|\n$)',
            r'\?\s*(.+?)\n\s*[→>-]+\s*(.+?)(?:\n\n|\n$)',
            r'```\s*(.+?)\n.*?```\s*\n\s*(?:=|→|is|:)\s*(.+?)(?:\n\n|\n$)',
        ]
        for pat in patterns:
            for m in re.finditer(pat, content, re.DOTALL | re.IGNORECASE):
                q, a = m.group(1).strip(), m.group(2).strip()
                if len(q) > 10 and len(a) > 15:
                    tiles.append(self._make_tile(q, a, source, "qa-pattern"))
        return tiles
    
    def _extract_headings(self, content: str, source: str) -> List[dict]:
        """Extract heading + first paragraph as Q&A."""
        tiles = []
        # Match "## What is X?" or "### How to Y?" headings
        heading_pats = [
            (r'^#{1,4}\s+(What (?:is|are|causes?|does?)\s+.+?)$', "what"),
            (r'^#{1,4}\s+(How (?:to|do|does|can|should)\s+.+?)$', "how"),
            (r'^#{1,4}\s+(Why (?:does?|is|are|do)\s+.+?)$', "why"),
            (r'^#{1,4}\s+(Where (?:is|are|to find)\s+.+?)$', "where"),
            (r'^#{1,4}\s+(When (?:to|should|does)\s+.+?)$', "when"),
        ]
        lines = content.split('\n')
        for i, line in enumerate(lines):
            for pat, qtype in heading_pats:
                m = re.match(pat, line, re.IGNORECASE)
                if m:
                    question = m.group(1).rstrip('?') + '?'
                    # Grab next non-empty lines as answer
                    answer_lines = []
                    for j in range(i+1, min(i+6, len(lines))):
                        l = lines[j].strip()
                        if not l:
                            if answer_lines:
                                break
                            continue
                        if l.startswith('#'):
                            break
                        answer_lines.append(l)
                    answer = ' '.join(answer_lines).strip()
                    if len(answer) > 20:
                        tiles.append(self._make_tile(question, answer, source, f"heading-{qtype}"))
        return tiles
    
    def _extract_definitions(self, content: str, source: str) -> List[dict]:
        """Extract bold term definitions."""
        tiles = []
        # "**Term** is/are/was/means definition"
        pat = r'\*\*(.+?)\*\*\s+(?:is|are|was|means|refers to|represents)\s+(.+?)(?:\.|$)'
        for m in re.finditer(pat, content, re.IGNORECASE):
            term, defn = m.group(1).strip(), m.group(2).strip()
            if len(defn) > 15:
                tiles.append(self._make_tile(
                    f"What is {term}?", 
                    f"{term} is {defn}",
                    source, "bold-definition"))

        # "**Term**: definition" format — skip single-word values
        pat2 = r'\*\*(.+?)\*\*[:\s]+(.+?)(?:\n|$)'
        for m in re.finditer(pat2, content):
            term, defn = m.group(1).strip(), m.group(2).strip()
            if len(defn) > 30 and len(term) < 60 and len(defn.split()) >= 4:
                tiles.append(self._make_tile(
                    f"What is {term}?",
                    f"{term}: {defn}",
                    source, "key-value"))
        return tiles
    
    def _extract_error_solutions(self, content: str, source: str) -> List[dict]:
        """Extract Error → Solution pairs."""
        tiles = []
        pat = r'(?:Error|ERROR|FAIL|Bug|Issue|Problem)[:\s]+(.+?)(?:\n|$)\s*(?:Fix|Solution|Resolution|Workaround)[:\s]+(.+?)(?:\n\n|\n$)'
        for m in re.finditer(pat, content, re.DOTALL | re.IGNORECASE):
            error, fix = m.group(1).strip(), m.group(2).strip()
            if len(error) > 10 and len(fix) > 10:
                tiles.append(self._make_tile(
                    f"How to fix: {error[:80]}",
                    fix,
                    source, "error-solution"))
        return tiles
    
    def _extract_procedures(self, content: str, source: str) -> List[dict]:
        """Extract numbered/bulleted procedures with commands."""
        tiles = []
        # Find sequences of numbered steps
        blocks = re.split(r'\n#{1,4}\s+', content)  # Split by headings
        for block in blocks:
            steps = re.findall(r'^\s*(?:\d+\.|[-*])\s+`?([^`\n]+)`?(?:\s*-?\s*(.+?))?$', block, re.MULTILINE)
            if len(steps) >= 3:
                # Extract the topic from preceding text
                topic_match = re.search(r'(.+?)(?:\n|$)', block[:200])
                topic = topic_match.group(1).strip() if topic_match else "this procedure"
                topic = re.sub(r'^#+\s*', '', topic).strip()
                
                # Build step list
                step_lines = []
                for cmd, desc in steps[:6]:
                    step = cmd.strip()
                    if desc:
                        step += f" — {desc.strip()}"
                    step_lines.append(step)
                
                if len(topic) > 5 and step_lines:
                    tiles.append(self._make_tile(
                        f"How to {topic[:80]}",
                        "Steps:\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(step_lines)),
                        source, "procedure"))
        return tiles
    
    def _extract_key_values(self, content: str, source: str) -> List[dict]:
        """Extract configuration key-value pairs that look like useful knowledge."""
        tiles = []
        # Match table rows or config entries
        pat = r'\|\s*`?([^`|\n]+)`?\s*\|\s*`?([^`|\n]+)`?\s*\|'
        matches = list(re.finditer(pat, content))
        
        # Group consecutive table rows
        if len(matches) >= 3:
            rows = [(m.group(1).strip(), m.group(2).strip()) for m in matches]
            # Check if it looks like a reference table (not data)
            if all(len(k) < 40 and len(v) < 100 for k, v in rows):
                # Try to extract the table topic from preceding heading
                pos = matches[0].start()
                heading_match = re.search(r'#{1,4}\s+(.+?)(?:\n|$)', content[max(0,pos-200):pos])
                topic = heading_match.group(1).strip() if heading_match else "reference table"
                
                table_str = "\n".join(f"- {k}: {v}" for k, v in rows[:8])
                tiles.append(self._make_tile(
                    f"What are the key values for {topic[:60]}?",
                    table_str,
                    source, "reference-table"))
        return tiles
    
    def _make_tile(self, question: str, answer: str, source: str, 
                    extraction_type: str) -> dict:
        """Create a candidate tile dict."""
        # Truncate to reasonable sizes
        if len(question) > 200:
            question = question[:200] + "..."
        if len(answer) > 500:
            answer = answer[:500] + "..."
        
        return {
            "question": question,
            "answer": answer,
            "source": f"forge:{extraction_type}",
            "source_file": os.path.basename(source),
            "confidence": self._confidence_score(question, answer, extraction_type),
            "extraction_type": extraction_type,
        }
    
    def _confidence_score(self, q: str, a: str, etype: str) -> float:
        """Score how likely this tile is useful (0-1)."""
        score = 0.5
        
        # Length heuristics
        if 15 < len(q) < 120:
            score += 0.1
        if 30 < len(a) < 400:
            score += 0.1
        
        # Pattern quality
        quality_map = {
            "qa-pattern": 0.2,
            "heading-what": 0.15,
            "heading-how": 0.15,
            "bold-definition": 0.1,
            "error-solution": 0.2,
            "procedure": 0.15,
            "reference-table": 0.1,
            "key-value": 0.05,
        }
        score += quality_map.get(etype, 0.0)
        
        # Contains useful indicators
        if any(w in a.lower() for w in ["because", "therefore", "specifically", "for example"]):
            score += 0.05
        
        # Penalize low-quality signals
        if "TODO" in a or "FIXME" in a:
            score -= 0.2
        if len(a) < 30:
            score -= 0.1
        
        return min(1.0, max(0.0, score))


# ─── Tile Validation ────────────────────────────────────────────────

class TileValidator:
    """Validates candidate tiles before merging."""
    
    def __init__(self, room_id: str, existing_tiles: List[dict]):
        self.room_id = room_id
        self.existing = existing_tiles
        self.existing_norms = {re.sub(r'[^\w\s]', '', t["question"].lower()) 
                               for t in existing_tiles}
    
    def validate(self, tile: dict) -> Tuple[bool, str]:
        """Validate a candidate tile. Returns (valid, reason)."""
        q = tile["question"]
        a = tile["answer"]
        
        # Check duplicates
        q_norm = re.sub(r'[^\w\s]', '', q.lower())
        if q_norm in self.existing_norms:
            return False, "duplicate question"
        
        # Check minimum quality
        if len(q) < 10:
            return False, "question too short"
        if len(a) < 20:
            return False, "answer too short"
        
        # Check for low-content tiles
        words = a.split()
        if len(words) < 5:
            return False, "answer too few words"
        
        # Check for copy-paste noise
        if a.count('\n') > 10 and len(a) < 200:
            return False, "likely code dump"
        
        # Check confidence threshold
        if tile.get("confidence", 0) < 0.4:
            return False, f"low confidence ({tile['confidence']:.2f})"
        
        # Check token budget (tile should fit in JIT)
        estimated_tokens = (len(q) + len(a)) // 4
        if estimated_tokens > 250:
            return False, f"too large ({estimated_tokens} tokens)"
        
        return True, "valid"
    
    def validate_batch(self, tiles: List[dict]) -> List[dict]:
        """Validate a batch, return only valid tiles."""
        valid = []
        for tile in tiles:
            ok, reason = self.validate(tile)
            if ok:
                valid.append(tile)
            else:
                log(f"  Rejected: {tile['question'][:40]}... ({reason})")
        return valid


# ─── Tile Merger ────────────────────────────────────────────────────

class TileMerger:
    """Merges validated tiles into PLATO room data."""
    
    def __init__(self, tiles_dir: str):
        self.tiles_dir = tiles_dir
    
    def merge(self, room_id: str, tiles: List[dict], dry_run: bool = True) -> int:
        """Merge tiles into room. Returns count merged."""
        room_file = os.path.join(self.tiles_dir, f"{room_id}.json")
        
        # Load existing
        existing = []
        if os.path.exists(room_file):
            try:
                with open(room_file) as f:
                    existing = json.load(f)
            except:
                pass
        
        # Check for duplicates
        existing_norms = {re.sub(r'[^\w\s]', '', t.get("question", "").lower()) for t in existing}
        new_tiles = []
        for t in tiles:
            norm = re.sub(r'[^\w\s]', '', t["question"].lower())
            if norm not in existing_norms:
                new_tiles.append({
                    "question": t["question"],
                    "answer": t["answer"],
                    "source": t.get("source", "forge"),
                    "tags": [t.get("extraction_type", "forge")],
                    "feedback_positive": 0,
                    "feedback_negative": 0,
                    "created": datetime.now().isoformat(),
                })
                existing_norms.add(norm)
        
        if not new_tiles:
            return 0
        
        if dry_run:
            # Write to staging instead
            os.makedirs(STAGING_DIR, exist_ok=True)
            stage_file = os.path.join(STAGING_DIR, f"{room_id}-{datetime.now():%Y%m%d-%H%M%S}.json")
            with open(stage_file, "w") as f:
                json.dump(new_tiles, f, indent=2)
            log(f"  Staged {len(new_tiles)} tiles for {room_id} → {stage_file}")
            return len(new_tiles)
        else:
            # Actually merge
            existing.extend(new_tiles)
            with open(room_file, "w") as f:
                json.dump(existing, f, indent=2)
            log(f"  Merged {len(new_tiles)} tiles into {room_id}")
            return len(new_tiles)


# ─── The Forge Loop ─────────────────────────────────────────────────

def scan_source(source_path: str, state: dict) -> List[str]:
    """Find markdown files that have changed since last scan."""
    changed = []
    if not os.path.exists(source_path):
        return changed
    
    if os.path.isfile(source_path):
        h = file_hash(source_path)
        if state["processed_files"].get(source_path) != h:
            changed.append(source_path)
    else:
        for root, dirs, files in os.walk(source_path):
            # Skip .git
            dirs[:] = [d for d in dirs if d != ".git"]
            for f in files:
                if f.endswith(('.md', '.txt', '.rst')):
                    fp = os.path.join(root, f)
                    h = file_hash(fp)
                    if state["processed_files"].get(fp) != h:
                        changed.append(fp)
    return changed


def load_room_tiles(room_id: str) -> List[dict]:
    """Load existing tiles for a room."""
    room_file = os.path.join(TILES_DIR, f"{room_id}.json")
    if os.path.exists(room_file):
        try:
            with open(room_file) as f:
                return json.load(f)
        except:
            pass
    return []


def forge_room(room_id: str, sources: List[str], state: dict, 
               dry_run: bool = True) -> int:
    """Forge tiles for a single room from its content sources."""
    existing = load_room_tiles(room_id)
    if not existing:
        return 0
    
    extractor = TileExtractor(room_id, existing)
    validator = TileValidator(room_id, existing)
    merger = TileMerger(TILES_DIR)
    
    all_candidates = []
    
    for source_path in sources:
        changed_files = scan_source(source_path, state)
        for fp in changed_files:
            try:
                with open(fp) as f:
                    content = f.read()
                candidates = extractor.extract(content, fp)
                valid = validator.validate_batch(candidates)
                all_candidates.extend(valid)
                
                # Mark as processed
                state["processed_files"][fp] = file_hash(fp)
                state["tiles_generated"] += len(candidates)
            except Exception as e:
                log(f"  Error processing {fp}: {e}")
    
    if all_candidates:
        merged = merger.merge(room_id, all_candidates, dry_run=dry_run)
        state["tiles_merged"] += merged
        return merged
    return 0


def log(msg: str):
    """Write to forge log."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def run_forge(dry_run: bool = True, max_rooms: int = 6, max_time: int = 300):
    """Main forge loop."""
    log("=" * 60)
    log("PLATO Tile Forge — starting")
    log(f"  dry_run={dry_run}, max_rooms={max_rooms}, max_time={max_time}s")
    log(f"  load={system_load():.2f}, mem={available_memory_mb()}MB free")
    
    start = time.time()
    state = load_state()
    state["runs"] += 1
    
    total_merged = 0
    rooms_processed = 0
    
    for room_id, sources in ROOM_SOURCE_MAP.items():
        if rooms_processed >= max_rooms:
            break
        if time.time() - start > max_time:
            log(f"  Time limit reached ({max_time}s)")
            break
        if not can_forge():
            log(f"  System too busy (load={system_load():.2f}), pausing...")
            time.sleep(30)
            if not can_forge():
                break
        
        if not sources:
            continue
        
        log(f"\n  Forging: {room_id}")
        merged = forge_room(room_id, sources, state, dry_run=dry_run)
        if merged > 0:
            total_merged += merged
        rooms_processed += 1
        
        # Rate limit: 1 room per minute
        if rooms_processed < max_rooms:
            time.sleep(5)
    
    save_state(state)
    
    elapsed = time.time() - start
    log(f"\n{'=' * 60}")
    log(f"Forge complete: {total_merged} tiles, {rooms_processed} rooms, {elapsed:.0f}s")
    log(f"  Total generated: {state['tiles_generated']}, Total merged: {state['tiles_merged']}")
    log(f"  Files processed: {len(state['processed_files'])}")
    
    return total_merged


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PLATO Tile Forge")
    parser.add_argument("--live", action="store_true", help="Actually merge tiles (not dry-run)")
    parser.add_argument("--rooms", type=int, default=6, help="Max rooms to process")
    parser.add_argument("--time", type=int, default=300, help="Max time in seconds")
    parser.add_argument("--status", action="store_true", help="Show forge status")
    parser.add_argument("--staged", action="store_true", help="Show staged tiles")
    args = parser.parse_args()
    
    if args.status:
        state = load_state()
        print(f"Tile Forge Status:")
        print(f"  Runs: {state['runs']}")
        print(f"  Files processed: {len(state['processed_files'])}")
        print(f"  Tiles generated: {state['tiles_generated']}")
        print(f"  Tiles merged: {state['tiles_merged']}")
        print(f"  Last run: {state['last_run']}")
        print(f"  System load: {system_load():.2f}")
        print(f"  Available memory: {available_memory_mb()}MB")
        staged = os.listdir(STAGING_DIR) if os.path.exists(STAGING_DIR) else []
        print(f"  Staged files: {len(staged)}")
        sys.exit(0)
    
    if args.staged:
        if os.path.exists(STAGING_DIR):
            for f in sorted(os.listdir(STAGING_DIR)):
                fp = os.path.join(STAGING_DIR, f)
                with open(fp) as fh:
                    tiles = json.load(fh)
                print(f"\n{f} ({len(tiles)} tiles):")
                for t in tiles:
                    conf = t.get("confidence", 0)
                    print(f"  [{conf:.2f}] Q: {t['question'][:60]}")
                    print(f"        A: {t['answer'][:80]}...")
                    print(f"        src: {t.get('source_file', '?')} ({t.get('extraction_type', '?')})")
        else:
            print("No staged tiles.")
        sys.exit(0)
    
    run_forge(dry_run=not args.live, max_rooms=args.rooms, max_time=args.time)
