"""
PLATO Room System — Spatial knowledge architecture.

Rooms are the cognitive spaces where tiles live. Each room has:
- A theme and description
- Connected exits to other rooms
- An NPC that greets visitors and answers questions
- A set of seed tiles for initial knowledge
- Permission levels (read, write, admin)
"""

import json, os, yaml
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, field


@dataclass
class Exit:
    direction: str
    target_room: str
    description: str = ""

    def to_dict(self):
        return {"direction": self.direction, "target_room": self.target_room,
                "description": self.description}


@dataclass
class NPC:
    name: str
    personality: str = ""
    greeting: str = "Welcome. How can I help?"
    system_prompt: str = ""
    model_tier: str = "tiny"  # tiny, mid, human

    def to_dict(self):
        return {"name": self.name, "personality": self.personality,
                "greeting": self.greeting, "system_prompt": self.system_prompt,
                "model_tier": self.model_tier}


@dataclass
class Room:
    room_id: str
    name: str
    description: str
    theme: str = ""  # novelist, classroom, business, game, harbor
    exits: List[Exit] = field(default_factory=list)
    npc: Optional[NPC] = None
    seed_tiles: List[dict] = field(default_factory=list)
    permissions: Dict[str, str] = field(default_factory=dict)  # visitor_id -> perm_level
    metadata: Dict = field(default_factory=dict)
    # Plato-First Runtime extensions
    state_diagram: str = ""   # Mermaid stateDiagram-v2 (optional)
    assertions_md: str = ""   # Assertive Markdown bullets (optional)

    def to_dict(self):
        return {
            "room_id": self.room_id,
            "name": self.name,
            "description": self.description,
            "theme": self.theme,
            "exits": [e.to_dict() for e in self.exits],
            "npc": self.npc.to_dict() if self.npc else None,
            "seed_tiles": self.seed_tiles,
            "permissions": self.permissions,
            "metadata": self.metadata,
            "state_diagram": self.state_diagram,
            "assertions_md": self.assertions_md
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Room":
        exits = [Exit(**e) for e in data.get("exits", [])]
        npc = NPC(**data["npc"]) if data.get("npc") else None
        return cls(
            room_id=data["room_id"],
            name=data["name"],
            description=data["description"],
            theme=data.get("theme", ""),
            exits=exits,
            npc=npc,
            seed_tiles=data.get("seed_tiles", []),
            permissions=data.get("permissions", {}),
            metadata=data.get("metadata", {}),
            state_diagram=data.get("state_diagram", ""),
            assertions_md=data.get("assertions_md", "")
        )


class RoomManager:
    """Load and manage room templates and runtime room state."""

    def __init__(self, rooms_dir: str = None):
        self.rooms_dir = Path(rooms_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"))
        self._rooms = {}  # room_id -> Room
        self._load_all()

    def _load_all(self):
        if not self.rooms_dir.exists():
            return
        # Load from subdirectories
        for theme_dir in self.rooms_dir.iterdir():
            if not theme_dir.is_dir():
                continue
            rooms_file = theme_dir / "rooms.yaml"
            if rooms_file.exists():
                with open(rooms_file) as f:
                    rooms_data = yaml.safe_load(f)
                if isinstance(rooms_data, list):
                    for rd in rooms_data:
                        room = Room.from_dict(rd)
                        self._rooms[room.room_id] = room
                elif isinstance(rooms_data, dict):
                    for rid, rd in rooms_data.items():
                        rd["room_id"] = rid
                        room = Room.from_dict(rd)
                        self._rooms[room.room_id] = room

    def get(self, room_id: str) -> Optional[Room]:
        return self._rooms.get(room_id)

    def get_by_theme(self, theme: str) -> List[Room]:
        return [r for r in self._rooms.values() if r.theme == theme]

    def get_starting_room(self, theme: str) -> Optional[Room]:
        """Get the default starting room for a theme."""
        themed = self.get_by_theme(theme)
        # Prefer rooms with 'start' in metadata or name
        for room in themed:
            if room.metadata.get("starting_room") or "entrance" in room.room_id.lower():
                return room
        return themed[0] if themed else None

    def all_rooms(self) -> Dict[str, Room]:
        return dict(self._rooms)

    def themes(self) -> List[str]:
        return sorted(set(r.theme for r in self._rooms.values() if r.theme))

    def get_exit_target(self, current_room_id: str, direction: str) -> Optional[str]:
        room = self._rooms.get(current_room_id)
        if not room:
            return None
        for exit in room.exits:
            if exit.direction.lower() == direction.lower():
                return exit.target_room
        return None

    def add_room(self, room: Room):
        self._rooms[room.room_id] = room
        # Persist to theme directory
        theme_dir = self.rooms_dir / (room.theme or "custom")
        theme_dir.mkdir(parents=True, exist_ok=True)
        rooms_file = theme_dir / "rooms.yaml"
        rooms_data = []
        if rooms_file.exists():
            with open(rooms_file) as f:
                rooms_data = yaml.safe_load(f) or []
        rooms_data.append(room.to_dict())
        with open(rooms_file, "w") as f:
            yaml.dump(rooms_data, f, default_flow_style=False)
