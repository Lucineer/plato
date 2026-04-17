"""
PLATO Audit Trail — Markdown-native observability.

Every action is appended to a structured Markdown log.
Debugging = reading a narrative. Rollback = deleting lines.

Design principles:
- Zero dependencies beyond stdlib
- Plain Markdown (human-readable, git-friendly, no DB)
- Append-only (O(1) writes, no locking needed)
- Structured enough for tool parsing, readable enough for humans
"""

import os, time, json
from datetime import datetime, timezone


class AuditLog:
    """Markdown-native audit trail for PLATO rooms."""

    def __init__(self, log_dir: str = "data/audit"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

    def _path(self, room_id: str) -> str:
        safe = room_id.replace("/", "_").replace("..", "")
        return os.path.join(self.log_dir, f"{safe}.md")

    def _ts(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _date(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _append(self, room_id: str, line: str):
        """Append a single audit line. O(1)."""
        path = self._path(room_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def session_start(self, room_id: str, visitor_id: str,
                      visitor_name: str, session_id: str):
        """Log a new session starting."""
        self._append(room_id, f"- [{self._ts()}] **SESSION** {visitor_name} ({visitor_id}) connected to `{room_id}` [session={session_id}]")

    def session_end(self, room_id: str, visitor_id: str, duration_sec: float):
        """Log a session ending."""
        self._append(room_id, f"- [{self._ts()}] **DISCONNECT** {visitor_id} after {duration_sec:.0f}s")

    def query(self, room_id: str, visitor_id: str, query: str, iteration: int):
        """Log an incoming query."""
        truncated = query[:120] + ("..." if len(query) > 120 else "")
        self._append(room_id, f"- [{self._ts()}] **QUERY** from {visitor_id} (iter={iteration}): \"{truncated}\"")

    def tile_match(self, room_id: str, tile_id: str, score: float, tier: str):
        """Log a tile match result."""
        emoji = "✅" if tier == "tiny" else "🤖" if tier == "mid" else "👤"
        self._append(room_id, f"- [{self._ts()}] {emoji} **TILE** {tile_id} matched (score={score:.2f}, tier={tier})")

    def no_match(self, room_id: str, query: str):
        """Log a query with no tile match."""
        truncated = query[:80] + ("..." if len(query) > 80 else "")
        self._append(room_id, f"- [{self._ts()}] ❌ **NO MATCH** for \"{truncated}\"")

    def clunk_signal(self, room_id: str, query: str, iteration: int):
        """Log a clunk signal (4+ iterations = gap detected)."""
        truncated = query[:80] + ("..." if len(query) > 80 else "")
        self._append(room_id, f"- [{self._ts()}] 🔔 **CLUNK** gap detected at iteration {iteration}: \"{truncated}\"")

    def new_tile(self, room_id: str, tile_id: str, source: str):
        """Log a new tile being created."""
        self._append(room_id, f"- [{self._ts()}] 🆕 **NEW TILE** {tile_id} (source={source})")

    def feedback(self, room_id: str, tile_id: str, positive: bool, old_score: float, new_score: float):
        """Log tile feedback (score update)."""
        arrow = "↑" if new_score > old_score else "↓"
        label = "positive" if positive else "negative"
        self._append(room_id, f"- [{self._ts()}] {arrow} **FEEDBACK** {tile_id}: {old_score:.2f} → {new_score:.2f} ({label})")

    def model_call(self, room_id: str, model: str, tokens: int, latency_ms: float):
        """Log an LLM API call."""
        self._append(room_id, f"- [{self._ts()}] 🧠 **LLM** {model} ({tokens} tokens, {latency_ms:.0f}ms)")

    def error(self, room_id: str, context: str, detail: str = ""):
        """Log an error."""
        self._append(room_id, f"- [{self._ts()}] ⚠️ **ERROR** {context}: {detail[:100]}")

    def room_move(self, visitor_id: str, from_room: str, to_room: str):
        """Log a visitor moving between rooms."""
        self._append(from_room, f"- [{self._ts()}] 🚪 **MOVE** {visitor_id} → `{to_room}`")
        self._append(to_room, f"- [{self._ts()}] 🚪 **ARRIVE** {visitor_id} from `{from_room}`")

    def stats_snapshot(self, room_id: str, stats: dict):
        """Log periodic stats snapshot."""
        self._append(room_id,
            f"- [{self._ts()}] 📊 **STATS** queries={stats.get('total_queries',0)} "
            f"tile_hits={stats.get('tiny_hits',0)} llm_calls={stats.get('mid_hits',0)} "
            f"new_tiles={stats.get('new_tiles',0)} clunks={len(stats.get('clunk_signals',[]))}"
        )

    def read(self, room_id: str, lines: int = 50) -> str:
        """Read the last N lines of a room's audit log."""
        path = self._path(room_id)
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])

    def read_session(self, room_id: str, session_id: str) -> str:
        """Read all audit lines for a specific session."""
        path = self._path(room_id)
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        return "".join(l for l in all_lines if session_id in l)

    def roll_back(self, room_id: str, keep_lines: int):
        """Roll back audit log to N lines. Returns removed lines."""
        path = self._path(room_id)
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        removed = all_lines[keep_lines:]
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(all_lines[:keep_lines])
        return "".join(removed)
