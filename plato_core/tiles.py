"""
PLATO Tile System — The atomic unit of accumulated experience.

A tile is a compressed unit of operational wisdom:
- Created by visitors, NPCs, or the system
- Retrieved by pattern matching (tiny model) or synthesis (mid-tier)
- Stores the answer, the context, the source, and the feedback signal
- Persists as JSON files, loadable into LoRA training data
"""

import json, os, time, hashlib
from pathlib import Path
from typing import Optional

TILES_DIR = os.environ.get("PLATO_TILES_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tiles"))


class Tile:
    """A single tile of accumulated experience."""

    def __init__(self, room_id: str, question: str, answer: str,
                 source: str = "visitor", tags: list = None,
                 context: str = "", parent_tile: str = None,
                 feedback_positive: int = 0, feedback_negative: int = 0,
                 tile_id: str = None, created: float = None, updated: float = None):
        self.room_id = room_id
        self.question = question
        self.answer = answer
        self.source = source  # visitor, npc, mid-tier, human, system
        self.tags = tags or []
        self.context = context
        self.parent_tile = parent_tile
        self.feedback_positive = feedback_positive
        self.feedback_negative = feedback_negative
        self.tile_id = tile_id or self._generate_id()
        self.created = created or time.time()
        self.updated = updated or time.time()

    def _generate_id(self) -> str:
        content = f"{self.room_id}:{self.question}:{self.answer}:{time.time()}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    @property
    def score(self) -> float:
        """Quality score based on feedback signals."""
        total = self.feedback_positive + self.feedback_negative
        if total == 0:
            return 0.5  # Neutral for new tiles
        return self.feedback_positive / total

    @property
    def is_popular(self) -> bool:
        return self.feedback_positive >= 5 and self.score >= 0.8

    def to_dict(self) -> dict:
        return {
            "tile_id": self.tile_id,
            "room_id": self.room_id,
            "question": self.question,
            "answer": self.answer,
            "source": self.source,
            "tags": self.tags,
            "context": self.context,
            "parent_tile": self.parent_tile,
            "feedback_positive": self.feedback_positive,
            "feedback_negative": self.feedback_negative,
            "created": self.created,
            "updated": self.updated
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Tile":
        return cls(**{k: v for k, v in data.items() if k in cls.__init__.__code__.co_varnames})

    def record_feedback(self, positive: bool):
        if positive:
            self.feedback_positive += 1
        else:
            self.feedback_negative += 1
        self.updated = time.time()


class TileStore:
    """Persistent tile storage backed by JSON files per room."""

    def __init__(self, tiles_dir: str = TILES_DIR):
        self.tiles_dir = Path(tiles_dir)
        self.tiles_dir.mkdir(parents=True, exist_ok=True)
        self._cache = {}  # room_id -> {tile_id -> Tile}

    def _room_file(self, room_id: str) -> Path:
        safe_name = room_id.replace("/", "_").replace(" ", "_").lower()
        return self.tiles_dir / f"{safe_name}.json"

    def _load_room(self, room_id: str) -> dict:
        if room_id in self._cache:
            return self._cache[room_id]
        f = self._room_file(room_id)
        if f.exists():
            with open(f) as fh:
                data = json.load(fh)
                tiles = {t["tile_id"]: Tile.from_dict(t) for t in data}
        else:
            tiles = {}
        self._cache[room_id] = tiles
        return tiles

    def _save_room(self, room_id: str):
        tiles = self._cache.get(room_id, {})
        f = self._room_file(room_id)
        with open(f, "w") as fh:
            json.dump([t.to_dict() for t in tiles.values()], fh, indent=2)

    def add(self, tile: Tile) -> str:
        room = self._load_room(tile.room_id)
        room[tile.tile_id] = tile
        self._save_room(tile.room_id)
        return tile.tile_id

    def get(self, room_id: str, tile_id: str) -> Optional[Tile]:
        room = self._load_room(room_id)
        return room.get(tile_id)

    def search(self, room_id: str, query: str, limit: int = 5) -> list:
        """Search tiles by question/answer text match. Tiny model does smarter matching."""
        room = self._load_room(room_id)
        query_lower = query.lower()
        scored = []
        for tile in room.values():
            # Simple keyword scoring (tiny model replaces this with embedding similarity)
            q_match = sum(1 for w in query_lower.split() if w in tile.question.lower())
            a_match = sum(1 for w in query_lower.split() if w in tile.answer.lower())
            tag_match = sum(1 for t in tile.tags if t.lower() in query_lower)
            total = q_match * 2 + a_match + tag_match
            if total > 0:
                scored.append((tile, total))
        scored.sort(key=lambda x: (x[1], x[0].score), reverse=True)
        return [t for t, s in scored[:limit]]

    def best_for_query(self, room_id: str, query: str, min_score: float = 0.6) -> Optional[Tile]:
        """Get the best tile for a query, or None if nothing good enough."""
        results = self.search(room_id, query, limit=3)
        for tile in results:
            if tile.score >= min_score:
                return tile
        return None

    def all_tiles(self, room_id: str) -> list:
        room = self._load_room(room_id)
        return sorted(room.values(), key=lambda t: str(t.created))

    def room_stats(self, room_id: str) -> dict:
        tiles = self.all_tiles(room_id)
        total = len(tiles)
        popular = sum(1 for t in tiles if t.is_popular)
        by_source = {}
        for t in tiles:
            by_source[t.source] = by_source.get(t.source, 0) + 1
        return {
            "total_tiles": total,
            "popular_tiles": popular,
            "sources": by_source,
            "total_feedback_positive": sum(t.feedback_positive for t in tiles),
            "total_feedback_negative": sum(t.feedback_negative for t in tiles)
        }

    def export_for_lora(self, room_id: str = None) -> list:
        """Export tiles as training data for LoRA fine-tuning."""
        entries = []
        rooms = [room_id] if room_id else [f.stem for f in self.tiles_dir.glob("*.json")]
        for rid in rooms:
            for tile in self._load_room(rid).values():
                entries.append({
                    "instruction": tile.question,
                    "input": tile.context,
                    "output": tile.answer,
                    "metadata": {
                        "room_id": rid,
                        "source": tile.source,
                        "score": tile.score,
                        "tags": tile.tags
                    }
                })
        return entries
