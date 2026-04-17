#!/usr/bin/env python3
"""
PLATO Harbor — OCR Dock Reader

Reads vessel names from camera feeds using OCR.
Creates tiles in the harbor_dock room for each reading.

Usage:
  python3 scripts/ocr_dock.py --camera http://camera-url/snapshot.jpg --position entrance
  python3 scripts/ocr_dock.py --camera /dev/video0 --position berth-3 --interval 60

Requirements:
  pip install pillow pytesseract  (for local OCR)
  OR set PLATO_OCR_API to a cloud OCR endpoint

Camera sources:
  - HTTP URL: fetches image from URL (IP camera snapshot endpoint)
  - /dev/video*: captures frame from V4L2 device
  - File path: reads image file (for testing)
"""

import argparse, json, os, sys, time, hashlib
from datetime import datetime, timezone


# ── Tile Store Interface ──
def load_tiles(tiles_dir: str, room_id: str) -> list:
    """Load tiles for a room."""
    path = os.path.join(tiles_dir, f"{room_id}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def save_tiles(tiles_dir: str, room_id: str, tiles: list):
    """Save tiles for a room."""
    os.makedirs(tiles_dir, exist_ok=True)
    path = os.path.join(tiles_dir, f"{room_id}.json")
    with open(path, "w") as f:
        json.dump(tiles, f, indent=2, default=str)


def create_tile(room_id: str, question: str, answer: str, source: str = "ocr",
                tags: list = None, context: str = "") -> dict:
    """Create a tile dict."""
    return {
        "tile_id": hashlib.sha256(f"{room_id}:{question}:{time.time()}".encode()).hexdigest()[:12],
        "room_id": room_id,
        "question": question,
        "answer": answer,
        "source": source,
        "tags": tags or [],
        "context": context,
        "score": 0.5,
        "feedback_positive": 0,
        "feedback_negative": 0,
        "created": datetime.now(timezone.utc).isoformat()
    }


def add_tile(tiles_dir: str, room_id: str, tile: dict) -> str:
    """Add a tile to the store. Returns tile_id."""
    tiles = load_tiles(tiles_dir, room_id)
    tiles.append(tile)
    save_tiles(tiles_dir, room_id, tiles)
    return tile["tile_id"]


def find_tile(tiles_dir: str, room_id: str, question_substring: str) -> dict | None:
    """Find a tile by question substring."""
    tiles = load_tiles(tiles_dir, room_id)
    for t in tiles:
        if question_substring in t.get("question", ""):
            return t
    return None


def update_tile(tiles_dir: str, room_id: str, tile_id: str, updates: dict):
    """Update a tile."""
    tiles = load_tiles(tiles_dir, room_id)
    for i, t in enumerate(tiles):
        if t.get("tile_id") == tile_id:
            tiles[i].update(updates)
            save_tiles(tiles_dir, room_id, tiles)
            return
    raise ValueError(f"Tile {tile_id} not found in {room_id}")


# ── OCR Engines ──

def ocr_tesseract(image_bytes: bytes, region: dict = None) -> dict:
    """Local OCR using Tesseract."""
    try:
        from PIL import Image
        import pytesseract
        import io

        img = Image.open(io.BytesIO(image_bytes))

        if region:
            img = img.crop((region["x"], region["y"], region["x"] + region["w"], region["y"] + region["h"]))

        # Preprocess: convert to grayscale, increase contrast
        img = img.convert("L")

        text = pytesseract.image_to_string(img, config="--psm 7")  # Single line mode

        return {
            "text": text.strip(),
            "confidence": 0.7,  # Tesseract doesn't give reliable per-word confidence
            "engine": "tesseract"
        }
    except ImportError:
        print("  ❌ Install: pip install pillow pytesseract")
        print("  Also install Tesseract: sudo apt install tesseract-ocr")
        return {"text": "", "confidence": 0, "engine": "tesseract", "error": "not installed"}
    except Exception as e:
        return {"text": "", "confidence": 0, "engine": "tesseract", "error": str(e)}


def ocr_cloud(image_bytes: bytes, api_url: str, api_key: str = None,
              region: dict = None) -> dict:
    """Cloud OCR via API endpoint (OpenAI-compatible or custom)."""
    import urllib.request
    import base64
    import json

    b64 = base64.b64encode(image_bytes).decode()

    payload = {
        "image": b64,
        "region": region
    }

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(api_url, data=json.dumps(payload).encode(), headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return {
                "text": result.get("text", "").strip(),
                "confidence": result.get("confidence", 0.5),
                "engine": "cloud"
            }
    except Exception as e:
        return {"text": "", "confidence": 0, "engine": "cloud", "error": str(e)}


def ocr_dummy(image_bytes: bytes) -> dict:
    """Dummy OCR for testing without cameras or engines."""
    return {
        "text": f"TEST-VESSEL-{hashlib.md5(image_bytes).hexdigest()[:6].upper()}",
        "confidence": 0.95,
        "engine": "dummy"
    }


# ── Camera Sources ──

def capture_http(url: str) -> bytes:
    """Fetch image from HTTP URL."""
    import urllib.request
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.read()


def capture_file(path: str) -> bytes:
    """Read image from file path."""
    with open(path, "rb") as f:
        return f.read()


def capture_v4l2(device: str) -> bytes:
    """Capture frame from V4L2 device using fswebcam or ffmpeg."""
    import subprocess, tempfile

    tmp = tempfile.mktemp(suffix=".jpg")

    # Try ffmpeg first
    try:
        subprocess.run(
            ["ffmpeg", "-f", "video4linux2", "-i", device, "-frames:v", "1", "-y", tmp],
            capture_output=True, timeout=5
        )
        with open(tmp, "rb") as f:
            data = f.read()
        os.unlink(tmp)
        return data
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Try fswebcam
    try:
        subprocess.run(["fswebcam", "-r", "1280x720", "--no-banner", tmp], capture_output=True, timeout=5)
        with open(tmp, "rb") as f:
            data = f.read()
        os.unlink(tmp)
        return data
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    print(f"  ❌ No capture tool found for {device}. Install ffmpeg or fswebcam.")
    return b""


def capture_source(source: str) -> bytes:
    """Auto-detect source type and capture."""
    if source.startswith("http://") or source.startswith("https://"):
        return capture_http(source)
    elif source.startswith("/dev/video"):
        return capture_v4l2(source)
    elif os.path.exists(source):
        return capture_file(source)
    else:
        print(f"  ❌ Unknown source: {source}")
        return b""


# ── Main Loop ──

def process_reading(tiles_dir: str, room_id: str, position: str,
                    vessel_name: str, confidence: float, engine: str,
                    snapshot_path: str = None, snapshot_data: bytes = None) -> dict:
    """Process an OCR reading into PLATO tiles."""

    timestamp = datetime.now(timezone.utc)
    tick = "✓" if confidence >= 0.7 else "?"

    # Save snapshot
    if snapshot_data and snapshot_path:
        os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)
        with open(snapshot_path, "wb") as f:
            f.write(snapshot_data)

    # Create movement tile
    question = f"Vessel sighting at {position}"
    answer = (
        f"{tick} {timestamp.strftime('%Y-%m-%d %H:%M UTC')} — "
        f"Vessel: {vessel_name} | Position: {position} | "
        f"Confidence: {confidence:.0%} | Engine: {engine}"
        + (f" | Snapshot: {os.path.basename(snapshot_path)}" if snapshot_path else "")
    )

    tile = create_tile(
        room_id=room_id,
        question=question,
        answer=answer,
        source="ocr",
        tags=["vessel", "ocr", position, vessel_name.lower()],
        context=f"OCR reading from {position} camera"
    )

    tile_id = add_tile(tiles_dir, room_id, tile)

    result = {
        "tile_id": tile_id,
        "vessel_name": vessel_name,
        "position": position,
        "timestamp": timestamp.isoformat(),
        "confidence": confidence,
        "confirmed": tick == "✓",
        "snapshot": snapshot_path
    }

    status = "✅" if tick == "✓" else "⚠️"
    print(f"  {status} [{tick}] {vessel_name} at {position} (conf: {confidence:.0%})")

    return result


def run_once(args):
    """Single OCR capture and processing."""
    print(f"📸 Capturing from {args.camera} ({args.position})...")

    image_data = capture_source(args.camera)
    if not image_data:
        print("  ❌ No image captured")
        return

    # OCR
    if args.dummy:
        result = ocr_dummy(image_data)
    elif args.ocr_api:
        result = ocr_cloud(image_data, args.ocr_api, args.ocr_key, args.region)
    else:
        result = ocr_tesseract(image_data, args.region)

    if not result.get("text"):
        print(f"  ❌ No text detected ({result.get('error', 'unknown')})")
        return

    # Save snapshot
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snapshot_path = None
    if args.snapshots:
        snapshot_path = os.path.join(args.snapshots, f"{timestamp}_{args.position}.jpg")

    # Process
    process_reading(
        tiles_dir=args.tiles_dir,
        room_id="harbor_dock",
        position=args.position,
        vessel_name=result["text"],
        confidence=result["confidence"],
        engine=result["engine"],
        snapshot_path=snapshot_path,
        snapshot_data=image_data
    )


def run_loop(args):
    """Continuous OCR monitoring loop."""
    print(f"🔄 Starting OCR monitoring: {args.camera} ({args.position}) every {args.interval}s")
    print(f"   Tiles dir: {args.tiles_dir}")
    if args.snapshots:
        print(f"   Snapshots: {args.snapshots}")
    print("   Press Ctrl+C to stop\n")

    last_hash = ""
    while True:
        try:
            image_data = capture_source(args.camera)
            if not image_data:
                time.sleep(args.interval)
                continue

            # Skip if image hasn't changed
            img_hash = hashlib.md5(image_data).hexdigest()
            if img_hash == last_hash:
                time.sleep(args.interval)
                continue
            last_hash = img_hash

            # OCR
            if args.dummy:
                result = ocr_dummy(image_data)
            elif args.ocr_api:
                result = ocr_cloud(image_data, args.ocr_api, args.ocr_key, args.region)
            else:
                result = ocr_tesseract(image_data, args.region)

            if not result.get("text"):
                time.sleep(args.interval)
                continue

            # Deduplicate: check if this vessel was already logged recently
            existing = find_tile(args.tiles_dir, "harbor_dock", f"Vessel sighting at {args.position}")
            if existing:
                last_vessel = existing["answer"].split("Vessel: ")[1].split(" |")[0] if "Vessel: " in existing["answer"] else ""
                if last_vessel == result["text"]:
                    time.sleep(args.interval)
                    continue

            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            snapshot_path = None
            if args.snapshots:
                snapshot_path = os.path.join(args.snapshots, f"{timestamp}_{args.position}.jpg")

            process_reading(
                tiles_dir=args.tiles_dir,
                room_id="harbor_dock",
                position=args.position,
                vessel_name=result["text"],
                confidence=result["confidence"],
                engine=result["engine"],
                snapshot_path=snapshot_path,
                snapshot_data=image_data
            )

        except KeyboardInterrupt:
            print("\n🛑 Stopped.")
            break
        except Exception as e:
            print(f"  ❌ Error: {e}")
            time.sleep(args.interval)


def main():
    parser = argparse.ArgumentParser(description="PLATO Harbor OCR Dock Reader")
    parser.add_argument("--camera", required=True, help="Camera source: URL, /dev/video*, or file path")
    parser.add_argument("--position", required=True, help="Camera position: entrance, berth-1, berth-2, etc.")
    parser.add_argument("--tiles-dir", default="data/tiles", help="Tiles directory")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between captures (loop mode)")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--snapshots", default=None, help="Directory to save camera snapshots")
    parser.add_argument("--ocr-api", default=None, help="Cloud OCR API endpoint")
    parser.add_argument("--ocr-key", default=None, help="Cloud OCR API key")
    parser.add_argument("--region", default=None, help="OCR crop region: x,y,w,h")
    parser.add_argument("--dummy", action="store_true", help="Use dummy OCR for testing")

    args = parser.parse_args()

    # Parse region
    if args.region:
        parts = args.region.split(",")
        args.region = {"x": int(parts[0]), "y": int(parts[1]), "w": int(parts[2]), "h": int(parts[3])}

    if args.loop:
        run_loop(args)
    else:
        run_once(args)


if __name__ == "__main__":
    main()
