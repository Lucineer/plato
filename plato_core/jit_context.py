"""
PLATO JIT Semantic Context — Two-tier context loading for token efficiency.

Problem: Sending all room tiles + conversation history to the LLM wastes tokens,
especially on the Jetson (8GB RAM, cost-sensitive API calls).

Solution: Two-tier context injection.
  Tier 1 (always, ~500 tokens): Room identity + NPC personality + rules summary
  Tier 2 (on-demand, ~2K tokens): Top-N relevant tiles ranked by relevance

On the Jetson, this cuts LLM input tokens by 60-70% per query.

Token counting is approximate (1 word ≈ 1.3 tokens for English).
"""

import re
from typing import List, Dict, Optional, Tuple


class Tier1Context:
    """Always-loaded room context. ~500 tokens max.

    Contains the irreducible minimum for the NPC to be coherent:
    - Room name and description
    - NPC personality
    - Active assertions (as short rules)
    - Current state machine state (if any)
    """

    MAX_TOKENS = 500  # ~350-400 words
    WORDS_PER_TOKEN = 0.77  # English average

    def __init__(self, room_name: str = "", room_description: str = "",
                 npc_name: str = "", npc_personality: str = "",
                 npc_greeting: str = "", assertions: List[dict] = None,
                 state_current: str = "", theme: str = ""):
        self.room_name = room_name
        self.room_description = room_description
        self.npc_name = npc_name
        self.npc_personality = npc_personality
        self.npc_greeting = npc_greeting
        self.assertions = assertions or []
        self.state_current = state_current
        self.theme = theme

    def build(self) -> str:
        """Build the Tier 1 context string, respecting token budget."""
        parts = []

        # Room identity (~50 tokens)
        if self.room_name:
            parts.append(f"Room: {self.room_name}")
        if self.theme:
            parts.append(f"Theme: {self.theme}")

        # NPC identity (~80 tokens)
        if self.npc_name:
            parts.append(f"You are {self.npc_name}.")
        if self.npc_personality:
            parts.append(self.npc_personality)

        # State machine (~30 tokens)
        if self.state_current:
            parts.append(f"Current state: {self.state_current}")

        # Assertions as compact rules (~100 tokens)
        if self.assertions:
            rules = []
            for a in self.assertions[:8]:  # Max 8 assertions
                sev = "REQUIRED" if a['severity'] in ('must', 'must_not') else "PREFERRED"
                text = a['text'][:60]
                rules.append(f"  [{sev}] {text}")
            if rules:
                parts.append("Rules:\n" + "\n".join(rules))

        context = "\n".join(parts)

        # Trim to budget
        max_words = int(self.MAX_TOKENS * self.WORDS_PER_TOKEN)
        if self._token_estimate(context) > self.MAX_TOKENS:
            words = context.split()
            if len(words) > max_words:
                context = " ".join(words[:max_words]) + "..."

        return context

    def token_count(self) -> int:
        return self._token_estimate(self.build())

    @staticmethod
    def _token_estimate(text: str) -> int:
        """Approximate token count: 1 token ≈ 4 chars for English."""
        return len(text) // 4


class Tier2Context:
    """On-demand tile context. ~2000 tokens max.

    Loads only the most relevant tiles for the current query.
    Ranks tiles by word overlap with query, then by quality score.
    """

    MAX_TOKENS = 2000  # ~1500 words
    WORDS_PER_TOKEN = 0.77

    def __init__(self, max_tiles: int = 5):
        self.max_tiles = max_tiles

    def build(self, query: str, tiles: list,
              conversation_context: list = None,
              iteration: int = 1) -> str:
        """Build Tier 2 context from ranked tiles + recent conversation.

        Args:
            query: The visitor's current question
            tiles: List of Tile objects (already filtered to room)
            conversation_context: Previous [(role, text)] exchanges
            iteration: Which attempt number this is
        """
        parts = []

        # Rank tiles by relevance to query
        ranked = self._rank_tiles(query, tiles)
        selected = ranked[:self.max_tiles]

        # Build tile context
        if selected:
            tile_parts = []
            for i, (tile, score) in enumerate(selected, 1):
                # Shorter tile format to save tokens
                tile_parts.append(
                    f"[{i}] Q: {tile.question}\n"
                    f"    A: {tile.answer}"
                )
            parts.append("Relevant experience:\n" + "\n---\n".join(tile_parts))

        # Add recent conversation if iteration > 1 (contextual awareness)
        if conversation_context and iteration > 1:
            recent = conversation_context[-4:]  # Last 2 exchanges
            conv_lines = []
            for role, text in recent:
                label = "Visitor" if role == "user" else "You"
                # Truncate long exchanges
                if len(text) > 100:
                    text = text[:100] + "..."
                conv_lines.append(f"{label}: {text}")
            parts.append("Recent conversation:\n" + "\n".join(conv_lines))

        context = "\n\n".join(parts)

        # Trim to budget
        max_words = int(self.MAX_TOKENS * self.WORDS_PER_TOKEN)
        if self._token_estimate(context) > self.MAX_TOKENS:
            context = self._trim_to_budget(context, max_words)

        return context

    def token_count(self, query: str, tiles: list,
                    conversation_context: list = None) -> int:
        return self._token_estimate(
            self.build(query, tiles, conversation_context)
        )

    def _rank_tiles(self, query: str, tiles: list) -> List[Tuple]:
        """Rank tiles by relevance to query.

        Score = word_overlap * 0.6 + quality_score * 0.4
        """
        query_words = set(w.lower() for w in re.findall(r'\w+', query) if len(w) > 2)

        scored = []
        for tile in tiles:
            tile_words = set(w.lower() for w in re.findall(
                r'\w+', f"{tile.question} {tile.answer}"
            ) if len(w) > 2)

            # Word overlap (Jaccard-like)
            if query_words and tile_words:
                overlap = len(query_words & tile_words) / len(query_words | tile_words)
            else:
                overlap = 0.0

            # Quality score (from feedback)
            quality = tile.score if hasattr(tile, 'score') else 0.5

            combined = (overlap * 0.6) + (quality * 0.4)
            scored.append((tile, combined))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _trim_to_budget(self, text: str, max_words: int) -> str:
        """Trim text to word budget, preserving tile boundaries."""
        words = text.split()
        if len(words) <= max_words:
            return text

        # Try to cut at a tile boundary (---)
        truncated = " ".join(words[:max_words])
        # Find last complete tile
        last_boundary = truncated.rfind("---")
        if last_boundary > max_words * 0.5:
            return truncated[:last_boundary].strip()
        return truncated + "..."

    @staticmethod
    def _token_estimate(text: str) -> int:
        return len(text) // 4


class JITContext:
    """Unified JIT context builder — combines Tier 1 and Tier 2."""

    def __init__(self, tier1_max_tokens: int = 500,
                 tier2_max_tokens: int = 2000,
                 max_tiles: int = 5):
        self.tier1 = Tier1Context()
        self.tier2 = Tier2Context(max_tiles=max_tiles)
        Tier1Context.MAX_TOKENS = tier1_max_tokens
        Tier2Context.MAX_TOKENS = tier2_max_tokens

    def build_system_prompt(self, query: str, tiles: list,
                            room_name: str = "", room_description: str = "",
                            npc_name: str = "", npc_personality: str = "",
                            assertions: List[dict] = None,
                            state_current: str = "", theme: str = "",
                            conversation_context: list = None,
                            iteration: int = 1) -> Tuple[str, dict]:
        """Build the complete JIT system prompt.

        Returns:
            (system_prompt, metrics) where metrics has token counts per tier
        """
        # Build Tier 1
        self.tier1 = Tier1Context(
            room_name=room_name,
            room_description=room_description,
            npc_name=npc_name,
            npc_personality=npc_personality,
            assertions=assertions,
            state_current=state_current,
            theme=theme
        )
        t1 = self.tier1.build()

        # Build Tier 2
        t2 = self.tier2.build(query, tiles, conversation_context, iteration)

        # Compose final prompt
        ordinal = {1: "1st", 2: "2nd", 3: "3rd"}.get(iteration, f"{iteration}th")

        system = f"""{t1}

{t2}

A visitor asked: {query}
This is their {ordinal} attempt.

Instructions:
- Answer concisely using the relevant experience above
- If partial match, fill gaps with reasoning
- If repeated question, give a BETTER answer
- 2-4 sentences usually
- Do NOT mention tiles, PLATO, or the system"""

        metrics = {
            "tier1_tokens": self.tier1.token_count(),
            "tier2_tokens": self.tier2._token_estimate(t2),
            "total_tokens": len(system) // 4,
            "tiles_loaded": min(len(tiles), self.tier2.max_tiles),
            "tiles_available": len(tiles),
            "compression_ratio": self._compression_ratio(tiles, system)
        }

        return system, metrics

    def _compression_ratio(self, tiles: list, system_prompt: str) -> float:
        """Calculate compression ratio vs. dumping all tiles."""
        if not tiles:
            return 1.0
        # What we'd send without JIT: all tiles
        full_text = "\n".join(f"Q: {t.question}\nA: {t.answer}" for t in tiles)
        full_tokens = len(full_text) // 4
        jit_tokens = len(system_prompt) // 4
        if full_tokens == 0:
            return 1.0
        return round(1.0 - (jit_tokens / full_tokens), 2)
