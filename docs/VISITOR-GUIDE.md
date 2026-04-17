# PLATO User Guide — For Visitors

*How to walk into a PLATO room and talk to the NPCs inside.*

## Connecting

```
telnet localhost 4040
```

You'll be asked a few onboarding questions (your name, purpose), then dropped into a room.

## The Basics

**Looking around:**
```
look          ← show room description, exits, NPC info
map           ← see all rooms and how they connect
who           ← see who's online
```

**Moving:**
```
north (or n)  ← go north
south (or s)  ← go south
east, west, up, down — you get it
```

**Talking to NPCs:**
```
ask What causes headaches?
ask How do I reset the system?
```
Or just type your question directly — anything that's not a command is treated as a question:
```
What causes headaches?
```
The NPC will answer. After each answer, you can type `yes` or `no` to give feedback (helps the room get smarter).

**Chatting in the room:**
```
say Hello everyone!
```

## Getting Better Answers

### Retry
Made a mistake? Want to see if the answer changed after you added tiles?
```
retry
```
Re-asks your last question.

### Teach
Just learned something the NPC should know? Teach it instantly:
```
teach The main entrance is on the north side, look for the blue door.
```
This creates a tile linked to your last question. Next time someone asks something similar, the NPC will use it.

### Add a Tile (more control)
```
add Q: Where is the entrance? A: The main entrance is on the north side.
```

### Search existing tiles
```
search headache
search reset
```

## Conversation Management

```
history    ← see your conversation with the NPC
clear      ← start fresh (forgets context, tiles persist)
```

## Giving Feedback

After each NPC answer, you'll see:
```
Was this helpful? Type 'yes' or 'no' to give feedback, or just continue.
```

- `yes` / `good` / `helpful` / `thanks` → marks the answer as good
- `no` / `bad` / `wrong` / `unhelpful` → marks it as needs improvement
- Type anything else (or wait) → skip feedback

This is how rooms learn what works and what doesn't. Please use it.

## Understanding NPC Answers

Each answer shows a tier:
- **📚 TINY** — matched an existing tile directly (fast, reliable)
- **🧠 MID** — NPC synthesized a new answer from multiple tiles (creative, creates new tiles)
- **👤 HUMAN** — NPC couldn't answer, needs a human to help

If you see `👤 HUMAN` a lot, the room needs more tiles. Use `health` to see what's missing.

## Word Anchors

You might notice `[BracketedWords]` in NPC answers. These are **word anchors** — self-referencing knowledge links. When the NPC mentions `[PaymentFlow]`, it's linking to related knowledge about payment flows. You don't need to do anything with them — they're how the NPC connects ideas across tiles.

## Quitting

```
quit
```

Your tiles persist. Your conversation doesn't. Come back anytime.

---

*PLATO v0.3.0 — The scripts keep running. The agent makes them better.*
