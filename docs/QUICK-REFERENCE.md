# PLATO Quick Reference Card

*Print this. Tape it to your monitor.*

## Connect
```
telnet localhost 4040
```

## Navigation
| Command | What it does |
|---------|-------------|
| `look` | Show room |
| `n` / `s` / `e` / `w` / `u` / `d` | Move |
| `map` | All rooms |
| `who` | Who's online |

## Talking
| Command | What it does |
|---------|-------------|
| `ask <question>` | Ask NPC |
| *(anything else)* | Also asks NPC |
| `say <msg>` | Chat in room |
| `retry` | Re-ask last Q |
| `history` | Conversation log |
| `clear` | Fresh start |

## Teaching
| Command | What it does |
|---------|-------------|
| `teach <answer>` | Quick-add tile (links to last Q) |
| `add Q: ... A: ...` | Add tile with Q+A |
| `search <word>` | Find tiles |
| `tiles` | List all tiles |

## Diagnostics
| Command | What it does |
|---------|-------------|
| `health` | Room score + tips |
| `stats` | Room + NPC numbers |
| `clunks` | Questions that failed |
| `audit` | Full event log |
| `state` | State machine |
| `assertions` | Safety rules |
| `episodes` | Muscle memory |
| `anchors` | Knowledge graph |

## Other
| Command | What it does |
|---------|-------------|
| `export` | Save tiles for LoRA |
| `help` | This list |
| `quit` | Leave |

## Answer Tiers
- 📚 **TINY** — matched a tile (fast, reliable)
- 🧠 **MID** — NPC synthesized from tiles (creative)
- 👤 **HUMAN** — couldn't answer, needs help

## Room YAML Structure
```yaml
- id: room-name
  name: Display Name
  description: Room description text
  exits:
    - direction: north
      target: other-room
  npc:
    name: BotName
    greeting: "Hello!"
    personality: "You are..."
  state_diagram: |
    stateDiagram-v2
      [*] --> Start
      Start --> End: done
  assertions_md: |
    - [MUST] always be polite
    - [SHOULD] offer alternatives
  seed_tiles:
    - question: "Q?"
      answer: "A."
      source: system
```

## Word Anchors
Put `[BracketedWords]` in tile answers. They auto-link to related tiles.

## Feedback
After each answer: `yes` = good, `no` = bad. This is how rooms learn.
