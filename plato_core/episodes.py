"""
PLATO Semantic Muscle Memory — Episode recorder for compiled experience.

When the NPC answers a question, the outcome (positive/negative feedback,
tile hit vs. synthesis, iterations) is recorded as an "episode" — a compressed
unit of "what worked." Future queries preload relevant episodes into JIT context.

The key insight: human expertise is chunked pattern recognition.
Episodes are the agent equivalent — not raw logs, but compressed lessons.

Episodes have a half-life: unused episodes decay (10%/week).
High-use episodes strengthen. This prevents stale knowledge from calcifying.
"""

import json, os, time, re, hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict


EPISODES_DIR = os.environ.get("PLATO_EPISODES_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "episodes"))

DECAY_RATE = 0.10        # 10% decay per week
MIN_SCORE = 0.05         # Below this, episode is pruned
MAX_EPISODES_PER_ROOM = 500


@dataclass
class Episode:
    """A compressed unit of 'what worked' for a type of question."""
    room_id: str
    query_pattern: str      # Canonical form of the question type
    answer_pattern: str     # What worked as a response
    outcome: str            # "positive", "negative", "neutral"
    tier: str               # "tiny" (tile hit), "mid" (synthesis), "human" (escalation)
    iterations: int         # How many tries it took
    tiles_used: List[str]   # Tile IDs that helped
    tags: List[str] = field(default_factory=list)
    use_count: int = 0      # How many times this episode was loaded
    strength: float = 1.0   # Decays with time, strengthens with use
    created: float = field(default_factory=time.time)
    last_used: float = 0.0
    episode_id: str = ""

    def __post_init__(self):
        if not self.episode_id:
            content = f"{self.room_id}:{self.query_pattern}:{time.time()}"
            self.episode_id = hashlib.sha256(content.encode()).hexdigest()[:10]

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop('episode_id', None)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Episode":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class EpisodeRecorder:
    """Records and retrieves experience episodes.

    Episodes are room-scoped. Each room has an episodes.json file.
    """

    def __init__(self, episodes_dir: str = None):
        self.episodes_dir = Path(episodes_dir or EPISODES_DIR)
        self.episodes_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, List[Episode]] = {}

    def _room_file(self, room_id: str) -> Path:
        safe = room_id.replace("/", "_").replace(" ", "_").lower()
        return self.episodes_dir / f"{safe}.json"

    def _load_room(self, room_id: str) -> List[Episode]:
        if room_id in self._cache:
            return self._cache[room_id]
        f = self._room_file(room_id)
        if f.exists():
            with open(f) as fh:
                data = json.load(fh)
            self._cache[room_id] = [Episode.from_dict(e) for e in data]
        else:
            self._cache[room_id] = []
        return self._cache[room_id]

    def _save_room(self, room_id: str):
        episodes = self._load_room(room_id)
        f = self._room_file(room_id)
        with open(f, "w") as fh:
            json.dump([e.to_dict() for e in episodes], fh, indent=2)

    def record(self, room_id: str, query: str, response: str,
               outcome: str, tier: str, iterations: int,
               tiles_used: List[str] = None, tags: List[str] = None) -> Episode:
        """Record a new episode from a query-response interaction.

        Args:
            room_id: The room this happened in
            query: The visitor's question
            response: The NPC's response
            outcome: "positive" (good feedback), "negative" (bad), "neutral"
            tier: "tiny", "mid", or "human"
            iterations: How many attempts this took
            tiles_used: Tile IDs that were used
            tags: Extracted tags
        """
        episode = Episode(
            room_id=room_id,
            query_pattern=self._canonize(query),
            answer_pattern=self._compress(response),
            outcome=outcome,
            tier=tier,
            iterations=iterations,
            tiles_used=tiles_used or [],
            tags=tags or self._extract_tags(query)
        )

        episodes = self._load_room(room_id)

        # Merge with similar existing episode (strengthen instead of duplicate)
        merged = False
        for existing in episodes:
            if self._is_similar(existing.query_pattern, episode.query_pattern):
                if outcome == "positive":
                    existing.strength = min(2.0, existing.strength + 0.2)
                elif outcome == "negative":
                    existing.strength = max(0.0, existing.strength - 0.3)
                existing.use_count += 1
                existing.last_used = time.time()
                merged = True
                episode = existing
                break

        if not merged:
            episodes.append(episode)
            # Prune old episodes if too many
            if len(episodes) > MAX_EPISODES_PER_ROOM:
                episodes.sort(key=lambda e: e.strength, reverse=True)
                self._cache[room_id] = episodes[:MAX_EPISODES_PER_ROOM]

        self._save_room(room_id)
        return episode

    def recall(self, room_id: str, query: str, limit: int = 3) -> List[Episode]:
        """Recall the most relevant episodes for a query.

        Returns episodes ranked by relevance × strength, with decay applied.
        """
        episodes = self._load_room(room_id)
        if not episodes:
            return []

        # Apply time decay
        now = time.time()
        for ep in episodes:
            age_days = (now - ep.created) / 86400
            age_weeks = age_days / 7
            ep.strength *= (1.0 - DECAY_RATE) ** age_weeks  # Exponential decay

        # Rank by relevance to query
        scored = []
        query_words = set(w.lower() for w in re.findall(r'\w+', query) if len(w) > 2)

        for ep in episodes:
            if ep.strength < MIN_SCORE:
                continue
            ep_words = set(w.lower() for w in re.findall(r'\w+', ep.query_pattern) if len(w) > 2)
            if query_words and ep_words:
                overlap = len(query_words & ep_words) / len(query_words | ep_words)
            else:
                overlap = 0.0

            # Combined score: relevance × strength × outcome_bonus
            outcome_bonus = 1.0 if ep.outcome != "negative" else 0.3
            score = (overlap * 0.5) + (ep.strength * 0.3) + (outcome_bonus * 0.2)
            scored.append((ep, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        # Mark as used and return
        results = []
        for ep, score in scored[:limit]:
            ep.use_count += 1
            ep.last_used = now
            results.append(ep)

        self._save_room(room_id)
        return results

    def recall_context(self, room_id: str, query: str, limit: int = 3) -> str:
        """Format recalled episodes as JIT context string."""
        episodes = self.recall(room_id, query, limit)
        if not episodes:
            return ""

        parts = []
        for ep in episodes:
            outcome_icon = "✅" if ep.outcome == "positive" else "⚠️" if ep.outcome == "negative" else "📝"
            parts.append(f"{outcome_icon} Similar question: {ep.query_pattern[:80]}")
            if ep.tier == "tiny":
                parts.append(f"   What worked: tile match ({ep.iterations} attempt{'s' if ep.iterations != 1 else ''})")
            elif ep.tier == "mid":
                parts.append(f"   What worked: synthesized answer ({ep.iterations} attempt{'s' if ep.iterations != 1 else ''})")
            parts.append(f"   Previous answer: {ep.answer_pattern[:120]}...")
            if ep.strength < 0.5:
                parts.append(f"   ⚠️ Low confidence (strength: {ep.strength:.2f})")

        return "Past experience:\n" + "\n".join(parts)

    def room_stats(self, room_id: str) -> dict:
        """Get episode statistics for a room."""
        episodes = self._load_room(room_id)
        if not episodes:
            return {"total": 0}

        positive = sum(1 for e in episodes if e.outcome == "positive")
        negative = sum(1 for e in episodes if e.outcome == "negative")
        avg_strength = sum(e.strength for e in episodes) / len(episodes)
        avg_use = sum(e.use_count for e in episodes) / len(episodes)

        return {
            "total": len(episodes),
            "positive": positive,
            "negative": negative,
            "avg_strength": round(avg_strength, 2),
            "avg_use_count": round(avg_use, 1),
            "decayed": sum(1 for e in episodes if e.strength < MIN_SCORE)
        }

    def _canonize(self, query: str) -> str:
        """Create a canonical form of a question (lowered, trimmed)."""
        return query.strip().lower()

    def _compress(self, response: str) -> str:
        """Compress a response to its essential pattern."""
        # Take first 200 chars — captures the core answer
        if len(response) <= 200:
            return response
        return response[:200] + "..."

    def _extract_tags(self, query: str) -> List[str]:
        """Extract tags from a query."""
        return [w.lower() for w in re.findall(r'\w+', query) if len(w) > 4][:5]

    def _is_similar(self, pattern1: str, pattern2: str) -> bool:
        """Check if two query patterns are similar enough to merge."""
        words1 = set(pattern1.split())
        words2 = set(pattern2.split())
        if not words1 or not words2:
            return False
        overlap = len(words1 & words2) / len(words1 | words2)
        return overlap > 0.6  # 60% word overlap = similar
