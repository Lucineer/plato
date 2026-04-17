"""
PLATO Telnet Server — The main interface for stepping into a PLATO.

Connect via: telnet localhost 4040
"""

import asyncio, sys, os, time, json
from plato_core.rooms import RoomManager
from plato_core.tiles import Tile, TileStore
from plato_core.npc import NPCLayer
from plato_core.onboard import onboard_questions, process_onboarding, detect_persona, PERSONAS


class PlatoSession:
    """A connected visitor's session."""

    def __init__(self, reader, writer, config, room_manager, tile_store):
        self.reader = reader
        self.writer = writer
        self.config = config
        self.room_manager = room_manager
        self.tile_store = tile_store
        self.npc = NPCLayer(config, tile_store)
        self.visitor = None
        self.current_room = None
        self.running = True
        # Pass room_manager for JIT Context Tier 1
        self.npc._room_manager = room_manager

    async def send(self, text: str):
        self.writer.write((text + "\r\n").encode("utf-8"))
        await self.writer.drain()

    async def send_ansi(self, text: str):
        """Send with ANSI color support."""
        self.writer.write((text + "\r\n").encode("utf-8"))
        await self.writer.drain()

    async def recv(self) -> str:
        data = await self.reader.readline()
        if not data:
            return ""
        return data.decode("utf-8", errors="replace").strip()

    async def onboard(self):
        """Interactive onboarding flow."""
        await self.send("\033[1;32m")
        await self.send("╔══════════════════════════════════════════╗")
        await self.send("║           P L A T O  v0.1.0             ║")
        await self.send("║    Git-Agent Maintenance Mode            ║")
        await self.send("╚══════════════════════════════════════════╝")
        await self.send("\033[0m")
        await self.send("")
        await self.send("Welcome. Let's get you oriented.")
        await self.send("")

        answers = {}
        questions = onboard_questions()

        for q in questions:
            if q.get("detect_persona") and "purpose" in answers:
                # Skip if already detected
                answers[q["id"]] = answers.get("purpose", "")
                continue

            await self.send(f"\033[1;36m{q['question']}\033[0m")
            if q.get("options"):
                for i, opt in enumerate(q["options"], 1):
                    await self.send(f"  {i}. {opt}")
            response = await self.recv()
            if not response:
                self.running = False
                return
            answers[q["id"]] = response

        # Detect persona from purpose
        if "purpose" in answers:
            answers["_persona"] = detect_persona(answers["purpose"])

        # Process onboarding
        profile = process_onboarding(answers, self.room_manager)
        self.visitor = profile

        # Save model endpoint if provided
        if answers.get("model_endpoint"):
            self.config["model_endpoint"] = answers["model_endpoint"]
            self.npc = NPCLayer(self.config, self.tile_store)

        # Place in starting room
        self.current_room = profile["starting_room"]

        # Load Plato-First Runtime extensions for starting room
        self._load_room_runtime(self.current_room)

        await self.send("")
        persona_info = PERSONAS.get(profile["persona"], PERSONAS["explorer"])
        await self.send(f"\033[1;33mDetected persona: {persona_info['description']}\033[0m")
        await self.send(f"\033[1;33mStarting room: {profile['starting_room']}\033[0m")
        await self.send("")
        await self.send(f"\033[1;32m{profile['greeting']}\033[0m")
        await self.send("")
        await self.send("Type \033[1mhelp\033[0m for commands. Type \033[1mlook\033[0m to see your surroundings.")

    async def look(self):
        """Show current room."""
        room = self.room_manager.get(self.current_room)
        if not room:
            await self.send("You're in a void. No room found.")
            return

        await self.send(f"\033[1;36m{room.name}\033[0m")
        await self.send(f"{room.description}")
        await self.send("")

        if room.exits:
            exits_str = ", ".join(f"\033[1m{e.direction}\033[0m" for e in room.exits)
            await self.send(f"Exits: {exits_str}")

        if room.npc:
            await self.send(f"\033[0;33m{room.npc.name}\033[0m is here. {room.npc.greeting}")

        stats = self.tile_store.room_stats(self.current_room)
        if stats["total_tiles"] > 0:
            await self.send(f"\033[2m[📊 {stats['total_tiles']} tiles, {stats['popular_tiles']} popular]\033[0m")

    async def move(self, direction: str):
        """Move to an adjacent room."""
        target = self.room_manager.get_exit_target(self.current_room, direction)
        if not target:
            await self.send(f"You can't go {direction}.")
            return

        self.current_room = target
        self._load_room_runtime(target)
        await self.look()

        # NPC greeting in new room
        room = self.room_manager.get(target)
        if room and room.npc:
            await self.send(f"\033[0;33m{room.npc.name}: {room.npc.greeting}\033[0m")

    async def say(self, text: str):
        """Say something in the room (visible to other visitors)."""
        await self.send(f"\033[1;34m{self.visitor['visitor_name']}\033[0m: {text}")

    def _load_room_runtime(self, room_id: str):
        """Load state machine and assertions for a room from its template."""
        room = self.room_manager.get(room_id)
        if not room:
            return
        if room.state_diagram or room.assertions_md:
            status = self.npc.load_room_runtime(
                room_id,
                state_diagram=room.state_diagram,
                assertions_md=room.assertions_md
            )

    async def ask(self, query: str):
        """Ask the room's NPC a question."""
        room = self.room_manager.get(self.current_room)
        personality = room.npc.personality if room and room.npc else ""

        result = self.npc.handle_query(self.current_room, self.visitor["visitor_id"], query, personality)

        tier_labels = {"tiny": "📚", "mid": "🧠", "human": "👤"}
        tier_icon = tier_labels.get(result["tier"], "❓")

        await self.send(f"\033[0;33m{tier_icon} [{result['tier'].upper()}]\033[0m {result['response']}")

        if result.get("new_tile_created"):
            await self.send("\033[2m[New tile created from this interaction]\033[0m")

        # Ask for feedback
        await self.send("\033[2mWas this helpful? Type 'yes' or 'no' to give feedback, or just continue.\033[0m")
        feedback = await asyncio.wait_for(self.recv(), timeout=10)
        if feedback:
            fb_lower = feedback.lower()
            if fb_lower in ("yes", "y", "good", "helpful", "thanks"):
                if result.get("tile_used"):
                    tile = self.tile_store.get(self.current_room, result["tile_used"])
                    if tile:
                        tile.record_feedback(True)
                await self.send("\033[2mThanks for the feedback! 🎉\033[0m")
            elif fb_lower in ("no", "n", "bad", "wrong", "unhelpful"):
                if result.get("tile_used"):
                    tile = self.tile_store.get(self.current_room, result["tile_used"])
                    if tile:
                        tile.record_feedback(False)
                await self.send("\033[2mNoted. A human can improve this tile later.\033[0m")

    async def add_tile(self, text: str):
        """Add a tile to the current room."""
        if ":" not in text and "?" not in text:
            await self.send("Format: add Q: <question> A: <answer>")
            return

        if ": " in text:
            parts = text.split(": ", 1)
            question = parts[0].lstrip("add ").strip()
            answer = parts[1].strip()
        else:
            question = text.lstrip("add ").strip()
            answer = ""

        if not answer:
            await self.send("Please provide an answer. Format: add Q: <question> A: <answer>")
            return

        tile = Tile(
            room_id=self.current_room,
            question=question,
            answer=answer,
            source=self.visitor["visitor_id"],
            context=f"Added by {self.visitor['visitor_name']} during session"
        )
        tile_id = self.tile_store.add(tile)
        await self.send(f"\033[1;32m✅ Tile added [{tile_id}]\033[0m")
        await self.send(f"   Q: {question}")
        await self.send(f"   A: {answer[:100]}{'...' if len(answer) > 100 else ''}")

    async def show_stats(self):
        """Show NPC/stats for current room."""
        stats = self.tile_store.room_stats(self.current_room)
        npc_stats = self.npc.get_stats()
        await self.send(f"\033[1;36m📊 Room Stats: {self.current_room}\033[0m")
        await self.send(f"  Tiles: {stats['total_tiles']}")
        await self.send(f"  Popular: {stats['popular_tiles']}")
        await self.send(f"  Sources: {stats['sources']}")
        await self.send(f"  Positive feedback: {stats['total_feedback_positive']}")
        await self.send(f"  Negative feedback: {stats['total_feedback_negative']}")
        await self.send(f"\033[1;36m🤖 NPC Stats\033[0m")
        await self.send(f"  Total queries: {npc_stats['total_queries']}")
        await self.send(f"  Tiny model hits: {npc_stats['tiny_hits']} ({npc_stats['tiny_rate']:.0%})")
        await self.send(f"  Mid-tier hits: {npc_stats['mid_hits']} ({npc_stats['mid_rate']:.0%})")
        await self.send(f"  Human escalations: {npc_stats['human_escapes']} ({npc_stats['escalation_rate']:.0%})")

    async def help(self):
        """Show available commands."""
        await self.send("\033[1;36mPLATO Commands:\033[0m")
        await self.send("  \033[1mlook\033[0m              Show current room")
        await self.send("  \033[1m<direction>\033[0m        Move (north, south, east, west, up, down)")
        await self.send("  \033[1mask <question>\033[0m   Ask the room's NPC")
        await self.send("  \033[1msay <message>\033[0m   Say something in the room")
        await self.send("  \033[1madd Q: ... A: ...\033[0m  Add a knowledge tile")
        await self.send("  \033[1mtiles\033[0m            List tiles in this room")
        await self.send("  \033[1mstats\033[0m            Show room and NPC stats")
        await self.send("  \033[1mwho\033[0m              Show visitors online")
        await self.send("  \033[1mmap\033[0m              Show room connections")
        await self.send("  \033[1mstate\033[0m            Show state machine (if active)")
        await self.send("  \033[1massertions\033[0m       Show assertions (if active)")
        await self.send("  \033[1mexport\033[0m           Export tiles for LoRA training")
        await self.send("  \033[1mquit\033[0m             Leave PLATO")

    async def list_tiles(self):
        """List tiles in current room."""
        tiles = self.tile_store.all_tiles(self.current_room)
        if not tiles:
            await self.send("No tiles in this room yet. Be the first to add one!")
            return
        await self.send(f"\033[1;36mTiles in {self.current_room} ({len(tiles)}):\033[0m")
        for t in tiles[-20:]:  # Last 20
            score_emoji = "🟢" if t.score >= 0.8 else "🟡" if t.score >= 0.5 else "🔴"
            await self.send(f"  {score_emoji} [{t.tile_id}] {t.question[:60]}...")
            await self.send(f"      ↳ {t.answer[:80]}{'...' if len(t.answer) > 80 else ''}")

    async def show_map(self):
        """Show room connections."""
        await self.send(f"\033[1;36m🗺️ PLATO Map (from {self.current_room}):\033[0m")
        for room_id, room in self.room_manager.all_rooms().items():
            marker = " ◀ YOU" if room_id == self.current_room else ""
            exits = ", ".join(e.direction for e in room.exits) if room.exits else "(no exits)"
            await self.send(f"  \033[1m{room.name}\033[0m [{room_id}]{marker}")
            await self.send(f"    → {exits}")

    async def show_room_state(self):
        """Show state machine state for current room."""
        state = self.npc.get_room_state(self.current_room)
        if not state:
            await self.send("No state machine active in this room.")
            return
        await self.send(f"\033[1;36m📊 State Machine: {self.current_room}\033[0m")
        await self.send(f"  Current: \033[1m{state['current']}\033[0m")
        await self.send(f"  Initial: {state['initial']} | Final: {state['final']}")
        await self.send(f"  States: {', '.join(state['states'])}")
        await self.send(f"  Transitions: {state['transitions']}")
        await self.send(f"  History: {state['history_length']} steps")

    async def show_room_assertions(self):
        """Show assertion engine status for current room."""
        info = self.npc.get_room_assertions(self.current_room)
        if not info:
            await self.send("No assertions active in this room.")
            return
        await self.send(f"\033[1;36m🛡️ Assertions: {self.current_room}\033[0m")
        await self.send(f"  Total: {info['total']} ({info['hard']} hard, {info['soft']} soft)")
        await self.send(f"  Violations: {info['violations_total']}")
        for a in info['assertions']:
            icon = "🔴" if a['severity'] in ('must', 'must_not') else "🟡"
            v = f" ({a['violations']} violations)" if a['violations'] > 0 else ""
            await self.send(f"  {icon} [{a['severity'].upper()}] {a['text'][:60]}{v}")

    async def handle_command(self, line: str):
        """Parse and execute a command."""
        if not line:
            return

        cmd = line.lower().split()[0]
        rest = line[len(cmd):].strip()

        if cmd in ("quit", "exit", "q"):
            self.running = False
            await self.send(f"\033[1;33mGoodbye, {self.visitor['visitor_name']}! Your tiles persist.\033[0m")
        elif cmd in ("look", "l"):
            await self.look()
        elif cmd in ("help", "h", "?"):
            await self.help()
        elif cmd in ("north", "south", "east", "west", "up", "down", "n", "s", "e", "w", "u", "d"):
            direction = {"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down"}.get(cmd, cmd)
            await self.move(direction)
        elif cmd == "ask" and rest:
            await self.ask(rest)
        elif cmd == "say" and rest:
            await self.say(rest)
        elif cmd.startswith("add ") or cmd == "add":
            await self.add_tile(rest)
        elif cmd == "tiles":
            await self.list_tiles()
        elif cmd == "stats":
            await self.show_stats()
        elif cmd == "map":
            await self.show_map()
        elif cmd in ("state", "!state"):
            await self.show_room_state()
        elif cmd in ("assertions", "!assertions"):
            await self.show_room_assertions()
        elif cmd == "who":
            await self.send(f"Visitors online: {self.visitor['visitor_name']}")
        elif cmd == "export":
            entries = self.tile_store.export_for_lora(self.current_room)
            export_file = os.path.join(self.config.get("tiles_dir", "data/tiles"),
                                       f"{self.current_room}_lora_export.json")
            os.makedirs(os.path.dirname(export_file), exist_ok=True)
            with open(export_file, "w") as f:
                json.dump(entries, f, indent=2)
            await self.send(f"\033[1;32mExported {len(entries)} tiles to {export_file}\033[0m")
        else:
            # Treat as a question to the NPC
            await self.ask(line)

    async def run(self):
        """Main session loop."""
        try:
            await self.onboard()
            if not self.running:
                return

            while self.running:
                line = await self.recv()
                if not line:
                    break
                await self.handle_command(line)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            try:
                await self.send(f"\033[31mError: {e}\033[0m")
            except:
                pass
        finally:
            self.writer.close()


async def handle_client(reader, writer, config, room_manager, tile_store):
    """Handle a new telnet connection."""
    session = PlatoSession(reader, writer, config, room_manager, tile_store)
    await session.run()


async def run_server(config: dict):
    """Start the PLATO telnet server."""
    host = config.get("host", "0.0.0.0")
    port = config.get("telnet_port", 4040)

    room_manager = RoomManager(config.get("rooms_dir"))
    tile_store = TileStore(config.get("tiles_dir"))

    # Seed default tiles if rooms exist
    for room_id, room in room_manager.all_rooms().items():
        if room.seed_tiles and tile_store.room_stats(room_id)["total_tiles"] == 0:
            for st in room.seed_tiles:
                tile = Tile(
                    room_id=room_id,
                    question=st.get("question", ""),
                    answer=st.get("answer", ""),
                    source=st.get("source", "system"),
                    tags=st.get("tags", []),
                    context=st.get("context", "")
                )
                tile_store.add(tile)

    print(f"\033[1;32mPLATO v0.1.0\033[0m — Git-Agent Maintenance Mode")
    print(f"Rooms loaded: {len(room_manager.all_rooms())}")
    print(f"Themes: {', '.join(room_manager.themes()) or 'none'}")
    print(f"Telnet: \033[1m{host}:{port}\033[0m")
    print(f"Tiles dir: {tile_store.tiles_dir}")
    print(f"Model: {config.get('model_endpoint', 'tile-only mode')}")
    print("")
    print("Connect: telnet localhost " + str(port))
    print("Press Ctrl+C to stop")
    print("")

    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, config, room_manager, tile_store),
        host, port
    )

    async with server:
        await server.serve_forever()
