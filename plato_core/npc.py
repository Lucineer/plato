"""
PLATO NPC Layer — Always-on tiny models that serve as room avatars.

Three tiers:
  - tiny: pattern-matches visitor questions against tiles (phi-4, Qwen-1.5B)
  - mid: synthesizes tiles + reasoning for novel questions (DeepSeek-chat, Qwen3-32B)
  - human: escalates to the captain with context and options
"""

import json, os, time, urllib.request, urllib.error
from typing import Optional, Tuple
from .tiles import Tile, TileStore


class NPCLayer:
    """Handles visitor questions through the tiered response system."""

    def __init__(self, config: dict = None, tile_store: TileStore = None):
        self.config = config or {}
        self.tile_store = tile_store or TileStore()
        self.model_endpoint = self.config.get("model_endpoint", "")
        self.model_key = self.config.get("model_key", "")
        self.model_name = self.config.get("model_name", "deepseek-chat")
        self.tiny_model = self.config.get("tiny_model", "")
        self.stats = {"tiny_hits": 0, "mid_hits": 0, "human_escapes": 0,
                      "new_tiles": 0, "total_queries": 0}

    def _call_model(self, prompt: str, system: str = "", model: str = None,
                    temperature: float = 0.7, max_tokens: int = 500) -> Optional[str]:
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
                     query: str, npc_personality: str = "") -> dict:
        """
        Process a visitor's question through the tiered system.

        Returns:
            {
                "response": str,
                "tier": "tiny" | "mid" | "human",
                "tile_used": str | None,
                "confidence": float,
                "new_tile_created": bool
            }
        """
        self.stats["total_queries"] += 1

        # TIER 1: Tiny model — pattern match against tiles
        best_tile = self.tile_store.best_for_query(room_id, query, min_score=0.4)

        if best_tile:
            self.stats["tiny_hits"] += 1
            # Enhance with NPC personality
            response = best_tile.answer
            if npc_personality and not response.startswith("["):
                response = self._add_personality(response, npc_personality)
            return {
                "response": response,
                "tier": "tiny",
                "tile_used": best_tile.tile_id,
                "confidence": best_tile.score,
                "new_tile_created": False
            }

        # TIER 2: Mid-tier — synthesize from tiles + reasoning
        related_tiles = self.tile_store.search(room_id, query, limit=3)

        if self.model_endpoint and related_tiles:
            synthesis = self._synthesize(room_id, query, related_tiles, npc_personality)
            if synthesis:
                self.stats["mid_hits"] += 1
                # Create a new tile from the synthesis
                new_tile = Tile(
                    room_id=room_id,
                    question=query,
                    answer=synthesis,
                    source="mid-tier",
                    context=f"Synthesized from tiles: {[t.tile_id for t in related_tiles]}"
                )
                self.tile_store.add(new_tile)
                self.stats["new_tiles"] += 1
                return {
                    "response": synthesis,
                    "tier": "mid",
                    "tile_used": None,
                    "confidence": 0.7,
                    "new_tile_created": True
                }

        # TIER 3: Human escalation
        self.stats["human_escapes"] += 1
        escalation = self._format_escalation(room_id, query, related_tiles, npc_personality)
        return {
            "response": escalation,
            "tier": "human",
            "tile_used": None,
            "confidence": 0.0,
            "new_tile_created": False
        }

    def _add_personality(self, response: str, personality: str) -> str:
        """Wrap a tile response in NPC personality."""
        if not personality:
            return response
        return f"{response}"

    def _synthesize(self, room_id: str, query: str, tiles: list,
                    personality: str) -> Optional[str]:
        """Use mid-tier model to synthesize an answer from related tiles."""
        tile_context = "\n".join([
            f"[Tile {t.tile_id}] Q: {t.question}\nA: {t.answer}"
            for t in tiles
        ])

        system = f"""You are an NPC in a PLATO room. A visitor asked: {query}

Here are relevant tiles from prior visitors:
{tile_context}

Synthesize a helpful answer drawing from these tiles. If the tiles partially answer the question, fill in the gaps with your reasoning. Be concise and specific. If you're not confident, say so."""
        if personality:
            system += f"\n\nYour personality: {personality}"

        return self._call_model(system=system, prompt=query, temperature=0.5)

    def _format_escalation(self, room_id: str, query: str,
                           related_tiles: list, personality: str) -> str:
        """Format a human escalation with context."""
        parts = [f"⚠️ This question needs a human response."]
        parts.append(f"\n📋 Visitor asked: {query}")

        if related_tiles:
            parts.append(f"\n📌 Related tiles found ({len(related_tiles)}):")
            for t in related_tiles:
                parts.append(f"  • [{t.tile_id}] {t.question[:60]}... (score: {t.score:.1f})")
        else:
            parts.append("\n📌 No related tiles found. This is a novel question.")

        parts.append(f"\n🔧 Recommended action: Add a tile for this question so future visitors get an instant answer.")

        return "\n".join(parts)

    def get_stats(self) -> dict:
        total = max(self.stats["total_queries"], 1)
        return {
            **self.stats,
            "tiny_rate": self.stats["tiny_hits"] / total,
            "mid_rate": self.stats["mid_hits"] / total,
            "escalation_rate": self.stats["human_escapes"] / total
        }
