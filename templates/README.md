# templates/

**The world.** Every room that exists in PLATO is defined here.

Each folder is a **theme** — a collection of rooms for a specific type of work. Each theme contains a `rooms.yaml` file with all its rooms. PLATO discovers them automatically.

## How to add a room

Open any `rooms.yaml`, add a room, restart PLATO. Done.

```yaml
my_new_room:
  room_id: my_new_room
  name: "My New Room"
  description: "What visitors see when they look around"
  theme: <current theme>
  npc:
    name: "The Guide"
    personality: "Helpful, domain-specific"
    greeting: "Welcome! What would you like to know?"
    model_tier: tiny
  exits:
    - direction: north
      target_room: plato_entrance
  seed_tiles:
    - question: "Common question here?"
      answer: "Helpful answer."
      source: system
      tags: [topic]
```

## How to create a theme

1. Create a folder: `templates/my-theme/`
2. Create `rooms.yaml` inside it
3. Add rooms
4. (Optional) Add an exit from `plato/rooms.yaml` to connect to the hub
5. Restart PLATO

That's it. No registration. No config. Just YAML.

## The Themes

### 🖊️ novelist/
The Writer's Study, Story Library, Character Gallery, World Map.
For world-building, character development, narrative craft.

### 🎓 classroom/
The Classroom, Study Room, Practice Lab, Teacher's Room.
For teaching, studying, learning.

### 💼 business/
Project Sandbox, Decision Log, Market Intelligence, Team Room.
For business planning, strategic decisions, team knowledge.

### 🎮 game/
Game Workshop, Level Studio, Systems Lab, NPC Forge.
For game design, level building, NPC behavior.

### ⚓ harbor/
Harbor Dock, Ship's Log, Berth Map, Camera Room.
For vessel tracking, OCR boat-name reading, movement logging.

### 💻 developer/
Developer Workshop, Decision Ledger, Debug Bench, Deployment Board.
For coding, debugging, architecture decisions, CI/CD.

### 🧭 plato/
PLATO Entrance — the hub connecting all themes.

## Room Anatomy

```yaml
room_id: my_room          # Unique identifier (URL-safe)
name: "Room Name"         # Display name
description: |            # What visitors see on 'look'
  A multi-line description
  of the room.
theme: my_theme           # Theme this room belongs to
metadata:                 # Optional metadata
  starting_room: false    # True = default for this theme's persona
npc:                      # The room's NPC
  name: "The Guide"       # Display name
  personality: "..."      # Personality description
  greeting: "..."         # First thing the NPC says
  system_prompt: "..."    # Prompt for mid-tier synthesis
  model_tier: tiny        # tiny | mid | human
exits:                    # Connections to other rooms
  - direction: north      # Cardinal or custom
    target_room: other    # Destination room_id
    description: "..."    # What visitors see
seed_tiles:               # Initial knowledge (loaded once)
  - question: "..."       # The question
    answer: "..."         # The answer
    source: system        # Who created it
    tags: [...]           # Searchable keywords
    context: "..."        # When/why this knowledge exists
```

## Design Principles

- **Rooms are data, not code.** A YAML file is all you need.
- **NPCs are stateless.** They read from tiles, they don't remember.
- **Exits are one-way declarations.** Each room lists its own exits.
- **Seed tiles are starter knowledge.** They load once per room.
- **Themes are organizational.** Any room can connect to any other.

---

*"Build the room. Stock it with knowledge. Open the door. Let experience accumulate."*
