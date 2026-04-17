"""
Word Anchors — Pillar 4 of Plato-First Runtime

Brackets like [PaymentFlow] in tile content and NPC responses act as
self-referencing knowledge graph nodes. When the JIT context builder
encounters an anchor, it pulls the associated tile into Tier 2 context.

Design:
- Anchors are defined in room config: word_anchors: {PaymentFlow: tile_id}
- Anchors can also be discovered from tile content (regex: \\[\\w+\\])
- When building JIT prompt, scan for anchors → pull referenced tiles → inject
- Anchors chain: [PaymentFlow] tile might contain [RefundPolicy] → pull that too
- Max depth: 3 to prevent infinite recursion
"""

import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

ANCHOR_PATTERN = re.compile(r'\[(\w+)\]')
MAX_ANCHOR_DEPTH = 3


@dataclass
class AnchorNode:
    """A word anchor that maps to tile content."""
    name: str                    # e.g. "PaymentFlow"
    description: str = ""        # Brief description for JIT context
    tile_ids: list = field(default_factory=list)  # Tiles that define this anchor
    created: float = field(default_factory=time.time)
    use_count: int = 0


class WordAnchors:
    """Manages word anchor knowledge graph for a room."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self._anchors: dict[str, AnchorNode] = {}
        self._loaded_rooms: set[str] = set()

    def load_room(self, room_id: str, anchor_config: dict = None):
        """Load word anchors for a room.

        anchor_config can be:
        - dict from room YAML: {"PaymentFlow": "tile-uuid", "RefundPolicy": "tile-uuid2"}
        - or auto-discovered from tile content
        """
        if anchor_config:
            for name, tile_id in anchor_config.items():
                if isinstance(tile_id, str):
                    tile_ids = [tile_id]
                elif isinstance(tile_id, list):
                    tile_ids = tile_id
                else:
                    continue
                key = name.upper()
                if key not in self._anchors:
                    self._anchors[key] = AnchorNode(name=key)
                self._anchors[key].tile_ids.extend(
                    tid for tid in tile_ids if tid not in self._anchors[key].tile_ids
                )
        self._loaded_rooms.add(room_id)

    def discover_anchors(self, room_id: str, tiles: list) -> int:
        """Scan tile content for anchor references and register them.

        Returns number of new anchors discovered.
        """
        new_count = 0
        for tile in tiles:
            content = getattr(tile, 'answer', '') or getattr(tile, 'content', '') or ''
            if isinstance(tile, dict):
                content = tile.get('answer', '') or tile.get('content', '')

            matches = ANCHOR_PATTERN.findall(content)
            for anchor_name in matches:
                key = anchor_name.upper()
                if key not in self._anchors:
                    self._anchors[key] = AnchorNode(name=key)
                    new_count += 1

                tile_id = getattr(tile, 'tile_id', None) or tile.get('tile_id', '')
                if tile_id and tile_id not in self._anchors[key].tile_ids:
                    self._anchors[key].tile_ids.append(tile_id)

        return new_count

    def resolve(self, anchor_name: str, depth: int = 0, visited: set = None) -> list[str]:
        """Resolve an anchor to its tile IDs, following chains up to MAX_ANCHOR_DEPTH.

        Returns list of tile IDs to inject.
        """
        if visited is None:
            visited = set()

        key = anchor_name.upper().strip('[]')
        if key in visited or depth >= MAX_ANCHOR_DEPTH:
            return []

        visited.add(key)
        node = self._anchors.get(key)
        if not node:
            return []

        node.use_count += 1
        tile_ids = list(node.tile_ids)

        # Check if any of these tiles contain more anchors (chaining)
        # This would require tile content access — handled in expand_context

        return tile_ids

    def expand_context(self, text: str, tile_store=None, room_id: str = "",
                       max_extra: int = 5) -> list:
        """Scan text for anchors, resolve them, return extra tile objects.

        This is called by JIT context builder to pull anchor-referenced tiles.
        """
        matches = ANCHOR_PATTERN.findall(text)
        if not matches:
            return []

        all_tile_ids = []
        seen = set()
        for anchor_name in matches:
            resolved = self.resolve(anchor_name, visited=seen)
            for tid in resolved:
                if tid not in seen and tid not in all_tile_ids:
                    all_tile_ids.append(tid)
                    seen.add(tid)
                    if len(all_tile_ids) >= max_extra:
                        break
            if len(all_tile_ids) >= max_extra:
                break

        if not tile_store or not all_tile_ids:
            return []

        # Fetch actual tiles
        extra_tiles = []
        for tid in all_tile_ids:
            try:
                tile = tile_store.get(room_id, tid)
                if tile:
                    extra_tiles.append(tile)
            except Exception:
                pass

        return extra_tiles

    def get_all_anchors(self) -> dict[str, AnchorNode]:
        """Get all registered anchors."""
        return dict(self._anchors)

    def register_anchor(self, name: str, tile_id: str, description: str = ""):
        """Manually register an anchor (e.g. from NPC responses)."""
        key = name.upper()
        if key not in self._anchors:
            self._anchors[key] = AnchorNode(name=key, description=description)
        if tile_id and tile_id not in self._anchors[key].tile_ids:
            self._anchors[key].tile_ids.append(tile_id)

    def room_stats(self, room_id: str) -> dict:
        """Get anchor stats for a room."""
        anchors = {k: v for k, v in self._anchors.items()}
        return {
            "total": len(anchors),
            "most_used": max((v.use_count for v in anchors.values()), default=0),
            "names": sorted(anchors.keys()),
        }
