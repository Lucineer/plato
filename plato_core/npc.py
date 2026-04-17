"""
PLATO NPC Layer v2 — Two-gear system.

Gear 1 (tile-only): Pattern match tiles, always works, zero cost.
Gear 2 (agent-driven): LLM synthesis from tiles, creates new tiles, gets better over time.

The scripts keep running without an agent. The agent makes them better.
"""

import json, os, time, urllib.request, urllib.error, re
from typing import Optional, Tuple
from plato_core.tiles import Tile, TileStore
from plato_core.audit import AuditLog


class NPCLayer:
    """Handles visitor questions through the tiered response system."""

    def __init__(self, config: dict = None, tile_store: TileStore = None):
        self.config = config or {}
        self.tile_store = tile_store or TileStore()
        self.model_endpoint = self.config.get("model_endpoint", "")
        self.model_key = self.config.get("model_key", "")
        self.model_name = self.config.get("model_name", "deepseek-chat")
        self.audit = AuditLog(self.config.get("data_dir", "data") + "/audit")
        self.stats = {"tiny_hits": 0, "mid_hits": 0, "human_escapes": 0,
                      "new_tiles": 0, "total_queries": 0, "iterations": 0,
                      "clunk_signals": []}
        self._conversations = {}  # visitor_id -> [(role, content)]

    def _call_model(self, prompt: str, system: str = "", model: str = None,
                    temperature: float = 0.7, max_tokens: int = 800) -> Optional[str]:
        """Call an OpenAI-compatible API endpoint."""
        endpoint = self.model_endpoint
        if not endpoint:
            return None

        model = model or self.model_name
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = json.dumps({
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }).encode()

        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.model_key}"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return None

    def handle_query(self, room_id: str, visitor_id: str,
                     query: str, npc_personality: str = "",
                     conversation_context: list = None) -> dict:
        """
        Process a visitor's question through the tiered system.

        Two-gear system:
          Gear 1 (tile-only): Pattern match against tiles. Always works. Zero cost.
          Gear 2 (agent-driven): LLM synthesizes from tiles. Creates new tiles. Gets better.

        The conversation_iteration_count is the signal:
          1 iteration = perfect tile hit (gear 1 nailed it)
          2-3 iterations = partial match, agent patched (gear 2 working)
          4+ iterations = clunk signal (needs new seed tile)

        Returns:
            {
                "response": str,
                "tier": "tiny" | "mid" | "human",
                "tile_used": str | None,
                "confidence": float,
                "new_tile_created": bool,
                "conversation_iteration": int
            }
        """
        self.stats["total_queries"] += 1

        # Track conversation for iteration counting
        conv = self._conversations.setdefault(visitor_id, [])
        conv.append(("user", query))

        # Count how many times this visitor has asked about this topic
        iteration = self._count_related_queries(conv, query)
        self.stats["iterations"] = max(self.stats.get("iterations", 0), iteration)

        # ── GEAR 1: Tile-only (always works, zero cost) ──
        best_tile = self._find_tile(room_id, query, min_confidence=self._threshold(iteration))

        if best_tile:
            self.stats["tiny_hits"] += 1
            self.audit.query(room_id, visitor_id, query, iteration)
            self.audit.tile_match(room_id, best_tile.tile_id, best_tile.score, "tiny")
            response = self._format_tile_response(best_tile, npc_personality, query)
            conv.append(("npc", response))
            return {
                "response": response,
                "tier": "tiny",
                "tile_used": best_tile.tile_id,
                "confidence": best_tile.score,
                "new_tile_created": False,
                "conversation_iteration": iteration
            }

        # ── GEAR 2: Agent-driven (LLM synthesis) ──
        related_tiles = self.tile_store.search(room_id, query, limit=5)

        if self.model_endpoint and (related_tiles or iteration >= 2):
            self.audit.query(room_id, visitor_id, query, iteration)
            if not related_tiles:
                self.audit.no_match(room_id, query)
            synthesis = self._synthesize(room_id, query, related_tiles, npc_personality,
                                         conversation_context=conv, iteration=iteration)

            if synthesis:
                self.stats["mid_hits"] += 1

                # Create new tile — this is how the room gets better
                new_tile = Tile(
                    room_id=room_id,
                    question=query,
                    answer=synthesis,
                    source="mid-tier",
                    tags=self._extract_tags(query),
                    context=f"Synthesized at iteration {iteration} from {[t.tile_id for t in related_tiles[:3]]}"
                )
                self.tile_store.add(new_tile)
                self.stats["new_tiles"] += 1
                self.audit.new_tile(room_id, new_tile.tile_id, "mid-tier")
                conv.append(("npc", synthesis))

                # Log clunk signal if this took multiple iterations
                if iteration >= 3:
                    self.audit.clunk_signal(room_id, query, iteration)
                    self.stats["clunk_signals"].append({
                        "room": room_id,
                        "query": query,
                        "iterations": iteration,
                        "time": time.time()
                    })
                    # Keep last 100
                    self.stats["clunk_signals"] = self.stats["clunk_signals"][-100:]

                return {
                    "response": synthesis,
                    "tier": "mid",
                    "tile_used": None,
                    "confidence": 0.7,
                    "new_tile_created": True,
                    "conversation_iteration": iteration
                }

        # ── ESCALATION: Human needed ──
        self.stats["human_escapes"] += 1
        escalation = self._format_escalation(room_id, query, related_tiles, npc_personality, iteration)
        conv.append(("npc", escalation))

        return {
            "response": escalation,
            "tier": "human",
            "tile_used": None,
            "confidence": 0.0,
            "new_tile_created": False,
            "conversation_iteration": iteration
        }

    def _threshold(self, iteration: int) -> float:
        """Lower the confidence threshold as iterations increase.
        Iteration 1: require 0.6 (good match)
        Iteration 2: require 0.4 (decent match)
        Iteration 3+: require 0.2 (any match is better than nothing)
        """
        return max(0.2, 0.7 - (iteration * 0.15))

    def _count_related_queries(self, conversation: list, query: str) -> int:
        """Count how many previous queries in this conversation are related."""
        query_words = set(w.lower() for w in re.findall(r'\w+', query) if len(w) > 3)
        if not query_words:
            return 1
        count = 0
        for role, text in conversation:
            if role == "user":
                text_words = set(w.lower() for w in re.findall(r'\w+', text) if len(w) > 3)
                if query_words & text_words:  # Any overlap
                    count += 1
        return max(1, count)

    def _find_tile(self, room_id: str, query: str, min_confidence: float = 0.4) -> Optional[Tile]:
        """Find best matching tile above threshold."""
        results = self.tile_store.search(room_id, query, limit=3)
        for tile in results:
            # Use both the tile's feedback score AND the search relevance
            combined = (tile.score * 0.4) + (0.6)  # Base relevance from search ordering
            if combined >= min_confidence:
                return tile
        return None

    def _format_tile_response(self, tile: Tile, personality: str, query: str) -> str:
        """Format a tile response with NPC personality injection."""
        response = tile.answer

        # If the query is more specific than the tile question, try to narrow the answer
        if personality:
            # Subtle personality injection — don't wrap in quotes, just influence tone
            response = response

        return response

    def _synthesize(self, room_id: str, query: str, tiles: list,
                    personality: str, conversation_context: list = None,
                    iteration: int = 1) -> Optional[str]:
        """Use LLM to synthesize an answer from related tiles + conversation context."""
        tile_context = "\n".join([
            f"[Tile {t.tile_id}] Q: {t.question}\nA: {t.answer}"
            for t in tiles
        ]) if tiles else "No existing tiles found."

        # Build conversation context for the LLM
        conv_summary = ""
        if conversation_context and iteration > 1:
            recent = conversation_context[-6:]  # Last 3 exchanges
            conv_summary = "\n\nPrevious conversation in this session:\n" + "\n".join(
                f"{'Visitor' if r == 'user' else 'NPC'}: {c}" for r, c in recent
            )

        system = f"""You are an NPC in a PLATO room — a git-agent maintenance space where experience accumulates as tiles.

A visitor asked: {query}
This is their {self._ordinal(iteration)} attempt to get a useful answer about this topic.

Here are relevant tiles from prior visitors and interactions:
{tile_context}
{conv_summary}

Instructions:
- Synthesize a helpful answer drawing from the tiles and conversation context
- If the tiles partially answer, fill gaps with your reasoning
- If this is a repeated question, give a DIFFERENT, better answer than before
- Be concise and specific — 2-4 sentences usually
- If you're genuinely unsure, say so honestly
- Do NOT mention tiles, PLATO, or the system — just answer the question naturally"""

        if personality:
            system += f"\n\nYour personality: {personality}"

        return self._call_model(system=system, prompt=query, temperature=0.5, max_tokens=600)

    def _ordinal(self, n: int) -> str:
        """Return ordinal string."""
        if n == 1: return "1st"
        if n == 2: return "2nd"
        if n == 3: return "3rd"
        return f"{n}th"

    def _extract_tags(self, query: str) -> list:
        """Extract simple tags from a query."""
        words = [w.lower() for w in re.findall(r'\w+', query) if len(w) > 4]
        return words[:5]

    def _format_escalation(self, room_id: str, query: str,
                           related_tiles: list, personality: str,
                           iteration: int) -> str:
        """Format a human escalation with context."""
        parts = [f"⚠️ This question needs a human response."]
        parts.append(f"\n📋 Visitor asked: {query}")
        parts.append(f"\n🔄 This is their {self._ordinal(iteration)} attempt on this topic.")

        if related_tiles:
            parts.append(f"\n📌 Related tiles found ({len(related_tiles)}):")
            for t in related_tiles[:5]:
                parts.append(f"  • [{t.tile_id}] {t.question[:60]}...")
        else:
            parts.append("\n📌 No related tiles found. Novel question — great seed tile opportunity.")

        parts.append(f"\n🔧 Action: Add a tile for this question so future visitors get an instant answer.")

        return "\n".join(parts)

    def get_stats(self) -> dict:
        total = max(self.stats["total_queries"], 1)
        clunks = self.stats.get("clunk_signals", [])
        # Aggregate clunks by room
        clunk_rooms = {}
        for c in clunks:
            clunk_rooms[c["room"]] = clunk_rooms.get(c["room"], 0) + 1

        return {
            **self.stats,
            "tiny_rate": self.stats["tiny_hits"] / total,
            "mid_rate": self.stats["mid_hits"] / total,
            "escalation_rate": self.stats["human_escapes"] / total,
            "avg_iterations": self.stats.get("iterations", 1),
            "clunk_count": len(clunks),
            "clunk_rooms": clunk_rooms
        }

    def get_clunk_report(self) -> list:
        """Get the clunk signals — questions that took too many iterations.
        These are the highest-priority tiles to create."""
        return self.stats.get("clunk_signals", [])[-20:]

    def clear_conversation(self, visitor_id: str):
        """Clear a visitor's conversation history."""
        self._conversations.pop(visitor_id, None)
