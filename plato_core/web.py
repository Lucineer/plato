"""
PLATO Web UI — Browser interface for PLATO rooms.

Run: python3 -m plato --web --port 8080
Open: http://localhost:8080
"""

import json, os, time, asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from plato_core.rooms import RoomManager
from plato_core.tiles import TileStore, Tile
from plato_core.npc import NPCLayer
from plato_core.onboard import detect_persona, onboard_questions, process_onboarding
from plato_core.jit_context import JITContext

# Public API key — set via PLATO_PUBLIC_API_KEY env var
PUBLIC_API_KEY = os.environ.get("PLATO_PUBLIC_API_KEY", "")


class PlatoWeb:
    """Web interface for PLATO."""

    def __init__(self, config: dict):
        self.config = config
        self.room_manager = RoomManager(config.get("rooms_dir"))
        self.tile_store = TileStore(config.get("tiles_dir"))
        self.npc = NPCLayer(config, self.tile_store)
        self.visitors = {}  # session_id -> visitor profile
        self.sessions = {}  # session_id -> {"room": str, "created": float}
        self._start_time = time.time()
        self._seed_tiles()

    def _seed_tiles(self):
        """Seed empty rooms with template tiles."""
        for room_id, room in self.room_manager.all_rooms().items():
            if room.seed_tiles and self.tile_store.room_stats(room_id)["total_tiles"] == 0:
                for st in room.seed_tiles:
                    tile = Tile(
                        room_id=room_id,
                        question=st.get("question", ""),
                        answer=st.get("answer", ""),
                        source=st.get("source", "system"),
                        tags=st.get("tags", []),
                        context=st.get("context", "")
                    )
                    self.tile_store.add(tile)

    def _new_session(self, session_id: str):
        """Create a new visitor session."""
        self.sessions[session_id] = {
            "room": "plato_entrance",
            "created": time.time(),
            "visitor_id": session_id[:8],
            "visitor_name": f"Visitor-{session_id[:6]}"
        }
        return self.sessions[session_id]

    def handle_api(self, path: str, method: str, body: dict = None, query: dict = None) -> dict:
        """Handle API requests. Returns dict with status and data."""

        # ── Info ──
        if path == "/api/info" and method == "GET":
            rooms = self.room_manager.all_rooms()
            themes = self.room_manager.themes()
            total_tiles = sum(
                self.tile_store.room_stats(rid)["total_tiles"]
                for rid in rooms
            )
            return {
                "status": "ok",
                "data": {
                    "version": "0.1.0",
                    "rooms": len(rooms),
                    "themes": themes,
                    "total_tiles": total_tiles,
                    "model": self.config.get("model_name", "tile-only"),
                    "modes": ["tile-only", "telnet", "web"]
                }
            }

        # ── Onboarding ──
        elif path == "/api/onboard" and method == "POST":
            session_id = body.get("session_id", os.urandom(8).hex())
            self._new_session(session_id)
            questions = onboard_questions()
            # Strip internal fields
            visible = [{"id": q["id"], "question": q["question"], "options": q.get("options", [])} for q in questions]
            return {
                "status": "ok",
                "data": {
                    "session_id": session_id,
                    "questions": visible
                }
            }

        elif path == "/api/onboard/submit" and method == "POST":
            session_id = body.get("session_id")
            answers = body.get("answers", {})
            if not session_id or session_id not in self.sessions:
                return {"status": "error", "error": "Invalid or expired session"}

            # Detect persona
            purpose = answers.get("purpose", "")
            answers["_persona"] = detect_persona(purpose)

            profile = process_onboarding(answers, self.room_manager)
            self.visitors[session_id] = profile
            self.sessions[session_id]["room"] = profile["starting_room"]
            self.sessions[session_id]["visitor_name"] = profile.get("visitor_name", "Visitor")
            self.sessions[session_id]["visitor_id"] = profile.get("visitor_id", session_id[:8])

            return {"status": "ok", "data": profile}

        # ── Rooms ──
        elif path == "/api/rooms" and method == "GET":
            rooms = []
            for rid, room in self.room_manager.all_rooms().items():
                stats = self.tile_store.room_stats(rid)
                rooms.append({
                    "room_id": rid,
                    "name": room.name,
                    "theme": room.theme,
                    "description": room.description[:200],
                    "npc": room.npc.name if room.npc else None,
                    "exits": [{"direction": e.direction, "target": e.target_room} for e in room.exits],
                    "tiles": stats["total_tiles"],
                    "popular": stats["popular_tiles"]
                })
            return {"status": "ok", "data": rooms}

        elif path == "/api/rooms/map" and method == "GET":
            map_data = {}
            for rid, room in self.room_manager.all_rooms().items():
                map_data[rid] = {
                    "name": room.name,
                    "theme": room.theme,
                    "exits": {e.direction: e.target_room for e in room.exits}
                }
            return {"status": "ok", "data": map_data}

        # ── Session: Look ──
        elif path == "/api/look" and method == "GET":
            session_id = query.get("session_id", [None])[0] if query else None
            if not session_id or session_id not in self.sessions:
                return {"status": "error", "error": "No active session. Start with /api/onboard."}

            room_id = self.sessions[session_id]["room"]
            room = self.room_manager.get(room_id)
            if not room:
                return {"status": "error", "error": f"Room {room_id} not found"}

            stats = self.tile_store.room_stats(room_id)
            return {
                "status": "ok",
                "data": {
                    "room_id": room_id,
                    "name": room.name,
                    "description": room.description,
                    "theme": room.theme,
                    "npc": {
                        "name": room.npc.name,
                        "greeting": room.npc.greeting
                    } if room.npc else None,
                    "exits": [{"direction": e.direction, "target": e.target_room, "description": e.description} for e in room.exits],
                    "stats": stats
                }
            }

        # ── Session: Move ──
        elif path == "/api/move" and method == "POST":
            session_id = body.get("session_id")
            direction = body.get("direction")
            if not session_id or session_id not in self.sessions:
                return {"status": "error", "error": "No active session"}

            current = self.sessions[session_id]["room"]
            target = self.room_manager.get_exit_target(current, direction)
            if not target:
                return {"status": "error", "error": f"Can't go {direction} from here."}

            self.sessions[session_id]["room"] = target
            room = self.room_manager.get(target)
            return {
                "status": "ok",
                "data": {
                    "room_id": target,
                    "name": room.name,
                    "description": room.description,
                    "npc": {"name": room.npc.name, "greeting": room.npc.greeting} if room.npc else None,
                    "exits": [{"direction": e.direction, "target": e.target_room} for e in room.exits]
                }
            }

        # ── Ask NPC ──
        elif path == "/api/ask" and method == "POST":
            session_id = body.get("session_id")
            question = body.get("question", "")
            if not session_id or session_id not in self.sessions:
                return {"status": "error", "error": "No active session"}

            room_id = self.sessions[session_id]["room"]
            visitor_id = self.sessions[session_id]["visitor_id"]
            room = self.room_manager.get(room_id)
            personality = room.npc.personality if room and room.npc else ""

            result = self.npc.handle_query(room_id, visitor_id, question, personality)
            return {"status": "ok", "data": result}

        # ── Add Tile ──
        elif path == "/api/tiles" and method == "POST":
            session_id = body.get("session_id")
            question = body.get("question", "")
            answer = body.get("answer", "")
            tags = body.get("tags", [])
            if not session_id or session_id not in self.sessions:
                return {"status": "error", "error": "No active session"}
            if not question or not answer:
                return {"status": "error", "error": "Question and answer required"}

            room_id = self.sessions[session_id]["room"]
            visitor_id = self.sessions[session_id]["visitor_id"]
            tile = Tile(
                room_id=room_id,
                question=question,
                answer=answer,
                source=visitor_id,
                tags=tags,
                context=f"Added via web UI"
            )
            tile_id = self.tile_store.add(tile)
            return {"status": "ok", "data": {"tile_id": tile_id}}

        # ── List Tiles ──
        elif path == "/api/tiles" and method == "GET":
            room_id = query.get("room_id", [None])[0] if query else None
            limit = int(query.get("limit", [20])[0]) if query else 20
            if not room_id:
                return {"status": "error", "error": "room_id required"}

            tiles = self.tile_store.all_tiles(room_id)[-limit:]
            return {
                "status": "ok",
                "data": [
                    {
                        "tile_id": t.tile_id,
                        "question": t.question,
                        "answer": t.answer[:200],
                        "source": t.source,
                        "score": t.score,
                        "tags": t.tags,
                        "created": t.created if isinstance(t.created, str) else str(t.created) if hasattr(t, 'created') else None
                    } for t in reversed(tiles)
                ]
            }

        # ── Feedback ──
        elif path == "/api/feedback" and method == "POST":
            tile_id = body.get("tile_id")
            positive = body.get("positive", True)
            if not tile_id:
                return {"status": "error", "error": "tile_id required"}

            # Find and update tile
            tile = self.tile_store.get_any(tile_id)
            if tile:
                tile.record_feedback(positive)
                return {"status": "ok", "data": {"tile_id": tile_id, "new_score": tile.score}}
            return {"status": "error", "error": "Tile not found"}

        # ── Stats ──
        elif path == "/api/stats" and method == "GET":
            room_id = query.get("room_id", [None])[0] if query else None
            if room_id:
                stats = self.tile_store.room_stats(room_id)
                npc_stats = self.npc.get_stats()
                return {"status": "ok", "data": {"room": stats, "npc": npc_stats}}

            # Global stats
            all_stats = {}
            for rid in self.room_manager.all_rooms():
                all_stats[rid] = self.tile_store.room_stats(rid)
            return {"status": "ok", "data": {"rooms": all_stats, "npc": self.npc.get_stats()}}

        # ── Export LoRA ──
        elif path == "/api/export" and method == "GET":
            room_id = query.get("room_id", [None])[0] if query else None
            entries = self.tile_store.export_for_lora(room_id)
            return {
                "status": "ok",
                "data": {
                    "count": len(entries),
                    "format": "instruction-input-output",
                    "entries": entries[:100]  # Cap preview
                }
            }

        # ── Search ──
        elif path == "/api/search" and method == "GET":
            room_id = query.get("room_id", [None])[0] if query else None
            q = query.get("q", [""])[0] if query else ""
            if not room_id or not q:
                return {"status": "error", "error": "room_id and q required"}

            results = self.tile_store.search(room_id, q, limit=10)
            return {
                "status": "ok",
                "data": [
                    {
                        "tile_id": t.tile_id,
                        "question": t.question,
                        "answer": t.answer[:200],
                        "score": t.score
                    } for t in results
                ]
            }

        return {"status": "error", "error": f"Unknown endpoint: {method} {path}"}

    # ── Public API (no session required, API key auth) ──

    def handle_public_api(self, path: str, method: str, body: dict = None,
                          query: dict = None, api_key: str = None) -> dict:
        """Public API endpoints for subcontractors and external tools.
        Auth: Bearer token or ?api_key= parameter matching PLATO_PUBLIC_API_KEY.
        If PLATO_PUBLIC_API_KEY is empty, public API is disabled."""

        if not PUBLIC_API_KEY:
            return {"status": "error", "error": "Public API not configured. Set PLATO_PUBLIC_API_KEY."}

        if api_key != PUBLIC_API_KEY:
            return {"status": "error", "error": "Invalid API key"}

        # ── v1/rooms — list all rooms with tile counts ──
        if path == "/v1/rooms" and method == "GET":
            rooms = []
            for rid, room in self.room_manager.all_rooms().items():
                stats = self.tile_store.room_stats(rid)
                rooms.append({
                    "room_id": rid,
                    "name": room.name,
                    "theme": room.theme,
                    "description": room.description,
                    "npc": room.npc.name if room.npc else None,
                    "npc_personality": room.npc.personality if room.npc else None,
                    "tiles": stats["total_tiles"],
                    "exits": {e.direction: e.target_room for e in room.exits},
                })
            return {"status": "ok", "data": rooms}

        # ── v1/room/{id}/tiles — get room tiles (paginated) ──
        elif path.startswith("/v1/room/") and "/tiles" in path and method == "GET":
            room_id = path.split("/v1/room/")[1].split("/tiles")[0]
            limit = int(query.get("limit", [50])[0]) if query else 50
            offset = int(query.get("offset", [0])[0]) if query else 0
            tiles = self.tile_store.all_tiles(room_id)
            total = len(tiles)
            page = tiles[offset:offset+limit]
            return {
                "status": "ok",
                "data": {
                    "room_id": room_id,
                    "total_tiles": total,
                    "offset": offset,
                    "limit": limit,
                    "tiles": [
                        {
                            "tile_id": t.tile_id,
                            "question": t.question,
                            "answer": t.answer,
                            "source": t.source,
                            "score": t.score,
                            "tags": t.tags,
                        } for t in page
                    ]
                }
            }

        # ── v1/room/{id}/context — JIT-compressed room context ──
        elif path.startswith("/v1/room/") and "/context" in path and method == "GET":
            room_id = path.split("/v1/room/")[1].split("/context")[0]
            room = self.room_manager.get(room_id)
            if not room:
                return {"status": "error", "error": f"Room {room_id} not found"}

            # Build JIT context
            jit = JITContext(
                room_name=room.name,
                room_description=room.description,
                npc_name=room.npc.name if room.npc else "",
                npc_personality=room.npc.personality if room.npc else "",
                npc_greeting=room.npc.greeting if room.npc else "",
                assertions=[],
                theme=room.theme,
            )

            # Get top tiles for context
            tiles = self.tile_store.all_tiles(room_id)
            top_tiles = sorted(tiles, key=lambda t: t.score, reverse=True)[:20]

            system_prompt, metrics = jit.build_system_prompt(
                room_id=room_id,
                tiles=[{"question": t.question, "answer": t.answer, "score": t.score}
                        for t in top_tiles],
                tier=2,  # Full context for subcontractors
            )

            return {
                "status": "ok",
                "data": {
                    "room_id": room_id,
                    "system_prompt": system_prompt,
                    "metrics": metrics,
                    "tiles_used": len(top_tiles),
                }
            }

        # ── v1/room/{id}/ask — ask the NPC directly (no session) ──
        elif path.startswith("/v1/room/") and "/ask" in path and method == "POST":
            room_id = path.split("/v1/room/")[1].split("/ask")[0]
            question = body.get("question", "")
            if not question:
                return {"status": "error", "error": "question required"}

            room = self.room_manager.get(room_id)
            if not room:
                return {"status": "error", "error": f"Room {room_id} not found"}

            personality = room.npc.personality if room.npc else ""
            result = self.npc.handle_query(room_id, "subcontractor", question, personality)
            return {"status": "ok", "data": result}

        # ── v1/search — cross-room tile search ──
        elif path == "/v1/search" and method == "GET":
            q = query.get("q", [""])[0] if query else ""
            room_id = query.get("room_id", [None])[0] if query else None
            if not q:
                return {"status": "error", "error": "q required"}

            if room_id:
                results = self.tile_store.search(room_id, q, limit=10)
                return {
                    "status": "ok",
                    "data": [
                        {"room_id": room_id, "question": t.question,
                         "answer": t.answer[:300], "score": t.score}
                        for t in results
                    ]
                }

            # Search all rooms
            all_results = []
            for rid in self.room_manager.all_rooms():
                results = self.tile_store.search(rid, q, limit=3)
                for t in results:
                    all_results.append({
                        "room_id": rid, "question": t.question,
                        "answer": t.answer[:300], "score": t.score
                    })
            all_results.sort(key=lambda x: x["score"], reverse=True)
            return {"status": "ok", "data": all_results[:15]}

        # ── v1/health ──
        elif path == "/v1/health" and method == "GET":
            rooms = self.room_manager.all_rooms()
            total_tiles = sum(self.tile_store.room_stats(rid)["total_tiles"] for rid in rooms)
            return {
                "status": "ok",
                "data": {
                    "version": "0.3.0",
                    "rooms": len(rooms),
                    "total_tiles": total_tiles,
                    "uptime": time.time() - self._start_time if hasattr(self, '_start_time') else 0,
                }
            }

        return {"status": "error", "error": f"Unknown endpoint: {method} {path}"}


# ── HTML Pages ──

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PLATO — Git-Agent Maintenance Mode</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0a0a0f; color: #e0e0e0; min-height: 100vh; }
.header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-bottom: 1px solid #2a2a4a; padding: 1.5rem 2rem; }
.header h1 { font-size: 1.5rem; color: #8be9fd; }
.header p { color: #6272a4; margin-top: 0.25rem; font-size: 0.9rem; }
.container { max-width: 1200px; margin: 0 auto; padding: 1.5rem; }
.grid { display: grid; grid-template-columns: 280px 1fr; gap: 1.5rem; }
@media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
.panel { background: #12121a; border: 1px solid #2a2a4a; border-radius: 8px; overflow: hidden; }
.panel-header { background: #1a1a2e; padding: 0.75rem 1rem; font-weight: 600; color: #8be9fd; border-bottom: 1px solid #2a2a4a; font-size: 0.85rem; }
.panel-body { padding: 1rem; }
.btn { background: #2a2a4a; color: #e0e0e0; border: 1px solid #3a3a5a; padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; transition: all 0.2s; }
.btn:hover { background: #3a3a5a; border-color: #8be9fd; }
.btn-primary { background: #1a3a5a; border-color: #8be9fd; color: #8be9fd; }
.btn-primary:hover { background: #2a4a6a; }
.btn-success { background: #1a3a2a; border-color: #50fa7b; color: #50fa7b; }
.btn-danger { background: #3a1a1a; border-color: #ff5555; color: #ff5555; }
.btn-sm { padding: 0.3rem 0.6rem; font-size: 0.8rem; }
input, textarea { background: #0a0a0f; border: 1px solid #2a2a4a; color: #e0e0e0; padding: 0.5rem 0.75rem; border-radius: 6px; width: 100%; font-size: 0.9rem; }
input:focus, textarea:focus { outline: none; border-color: #8be9fd; }
textarea { resize: vertical; min-height: 60px; font-family: inherit; }
.room-list { list-style: none; }
.room-item { padding: 0.6rem 0.75rem; border-bottom: 1px solid #1a1a2e; cursor: pointer; transition: background 0.2s; font-size: 0.85rem; }
.room-item:hover { background: #1a1a2e; }
.room-item.active { background: #1a2a3a; border-left: 3px solid #8be9fd; }
.room-item .room-name { color: #f8f8f2; }
.room-item .room-theme { color: #6272a4; font-size: 0.75rem; }
.room-item .room-tiles { color: #50fa7b; font-size: 0.75rem; float: right; }
.chat { display: flex; flex-direction: column; height: calc(100vh - 200px); }
.chat-messages { flex: 1; overflow-y: auto; padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; }
.msg { max-width: 85%; padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; line-height: 1.5; }
.msg-system { background: #1a1a2e; border: 1px solid #2a2a4a; color: #8be9fd; align-self: center; font-size: 0.8rem; }
.msg-npc { background: #1a2a3a; border: 1px solid #2a3a4a; align-self: flex-start; }
.msg-npc .msg-label { color: #ffb86c; font-weight: 600; font-size: 0.8rem; margin-bottom: 0.25rem; }
.msg-npc .msg-tier { color: #6272a4; font-size: 0.7rem; }
.msg-user { background: #2a2a3a; border: 1px solid #3a3a4a; align-self: flex-end; }
.msg-tile { background: #1a2a1a; border: 1px solid #2a3a2a; align-self: flex-start; }
.msg-tile .tile-q { color: #f1fa8c; font-weight: 600; font-size: 0.85rem; }
.msg-tile .tile-a { color: #e0e0e0; margin-top: 0.25rem; }
.chat-input { padding: 0.75rem; border-top: 1px solid #2a2a4a; display: flex; gap: 0.5rem; }
.chat-input input { flex: 1; }
.exits { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.5rem; }
.exit-btn { font-size: 0.8rem; }
.badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 10px; font-size: 0.7rem; font-weight: 600; }
.badge-tiny { background: #1a2a1a; color: #50fa7b; }
.badge-mid { background: #2a2a1a; color: #f1fa8c; }
.badge-human { background: #2a1a2a; color: #ff79c6; }
.feedback-row { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.75rem; }
.stat-card { background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 6px; padding: 0.75rem; text-align: center; }
.stat-value { font-size: 1.5rem; font-weight: 700; color: #8be9fd; }
.stat-label { font-size: 0.75rem; color: #6272a4; margin-top: 0.25rem; }
#onboard { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
#onboard .card { background: #12121a; border: 1px solid #2a2a4a; border-radius: 12px; padding: 2rem; max-width: 500px; width: 90%; }
#onboard h2 { color: #8be9fd; margin-bottom: 0.5rem; }
#onboard p { color: #6272a4; margin-bottom: 1.5rem; }
.onboard-field { margin-bottom: 1rem; }
.onboard-field label { display: block; color: #e0e0e0; margin-bottom: 0.3rem; font-size: 0.85rem; }
.onboard-field .hint { color: #6272a4; font-size: 0.75rem; margin-top: 0.2rem; }
.hidden { display: none !important; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #0a0a0f; }
::-webkit-scrollbar-thumb { background: #2a2a4a; border-radius: 3px; }
</style>
</head>
<body>

<!-- Onboarding Screen -->
<div id="onboard">
  <div class="card">
    <h2>⚡ PLATO</h2>
    <p>Git-Agent Maintenance Mode</p>
    <div id="onboard-form">
      <div class="onboard-field">
        <label>Your name</label>
        <input id="ob-name" placeholder="What should we call you?" autofocus>
      </div>
      <div class="onboard-field">
        <label>What brings you here?</label>
        <textarea id="ob-purpose" rows="2" placeholder="I'm building a... / I need help with... / I want to learn about..."></textarea>
        <div class="hint">We'll use this to place you in the right room</div>
      </div>
      <div class="onboard-field">
        <label>Experience level</label>
        <input id="ob-exp" placeholder="First time / Experienced / Expert">
      </div>
      <div class="onboard-field">
        <label>API endpoint (optional)</label>
        <input id="ob-model" placeholder="https://api.example.com/v1/chat/completions">
        <div class="hint">Leave blank for tile-only mode (no API needed)</div>
      </div>
      <button class="btn btn-primary" style="width:100%" onclick="submitOnboard()">Enter PLATO →</button>
    </div>
  </div>
</div>

<!-- Main Interface -->
<div id="app" class="hidden">
  <div class="header">
    <h1>⚡ PLATO <span id="header-room" style="color:#f8f8f2;font-weight:400"></span></h1>
    <p id="header-desc"></p>
  </div>
  <div class="container">
    <div class="grid">
      <!-- Sidebar -->
      <div>
        <div class="panel" style="margin-bottom:1rem">
          <div class="panel-header">🗺️ Rooms</div>
          <div class="panel-body" style="padding:0.5rem;max-height:400px;overflow-y:auto">
            <ul class="room-list" id="room-list"></ul>
          </div>
        </div>
        <div class="panel">
          <div class="panel-header">📊 Stats</div>
          <div class="panel-body">
            <div class="stats-grid" id="stats-grid"></div>
          </div>
        </div>
      </div>

      <!-- Chat -->
      <div class="panel">
        <div class="panel-header">
          <span id="chat-room-name">Loading...</span>
          <span id="chat-npc" style="color:#ffb86c;margin-left:1rem"></span>
        </div>
        <div class="chat">
          <div class="chat-messages" id="chat-messages"></div>
          <div class="chat-input">
            <input id="chat-input" placeholder="Ask a question or type a command..." onkeydown="if(event.key==='Enter')sendMsg()">
            <button class="btn btn-primary" onclick="sendMsg()">Send</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
const API = '';
let sessionId = null;
let currentRoom = null;

// ── Onboarding ──
async function submitOnboard() {
  const name = document.getElementById('ob-name').value.trim() || 'Visitor';
  const purpose = document.getElementById('ob-purpose').value.trim() || 'exploring';
  const experience = document.getElementById('ob-exp').value.trim() || 'first time';
  const model = document.getElementById('ob-model').value.trim();

  let sid;
  try {
    const r = await fetch(API + '/api/onboard', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({}) });
    const d = await r.json();
    sid = d.data.session_id;
  } catch(e) { sid = crypto.randomUUID(); }

  try {
    const r = await fetch(API + '/api/onboard/submit', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ session_id: sid, answers: { name, purpose, experience, model_endpoint: model } })
    });
    const d = await r.json();
    if (d.status === 'ok') {
      sessionId = sid;
      currentRoom = d.data.starting_room;
      enterPlato(d.data);
    } else {
      alert('Error: ' + (d.error || 'unknown'));
    }
  } catch(e) { alert('Connection error: ' + e.message); }
}

// ── Enter PLATO ──
function enterPlato(profile) {
  document.getElementById('onboard').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  addSystemMsg(profile.greeting || 'Welcome to PLATO.');
  loadRooms();
  loadRoom();
}

// ── Load room list ──
async function loadRooms() {
  try {
    const r = await fetch(API + '/api/rooms');
    const d = await r.json();
    const list = document.getElementById('room-list');
    list.innerHTML = '';
    d.data.forEach(r => {
      const li = document.createElement('li');
      li.className = 'room-item' + (r.room_id === currentRoom ? ' active' : '');
      li.innerHTML = '<span class="room-name">' + r.name + '</span><br><span class="room-theme">' + r.theme + '</span><span class="room-tiles">' + r.tiles + ' tiles</span>';
      li.onclick = () => moveTo(r.room_id);
      list.appendChild(li);
    });
  } catch(e) {}
}

// ── Load current room ──
async function loadRoom() {
  try {
    const r = await fetch(API + '/api/look?session_id=' + sessionId);
    const d = await r.json();
    if (d.status === 'ok') {
      const room = d.data;
      currentRoom = room.room_id;
      document.getElementById('header-room').textContent = '— ' + room.name;
      document.getElementById('header-desc').textContent = room.description.substring(0, 120);
      document.getElementById('chat-room-name').textContent = room.name;
      document.getElementById('chat-npc').textContent = room.npc ? room.npc.name : '';

      // NPC greeting
      if (room.npc) {
        addNpcMsg(room.npc.name, room.npc.greeting, null);
      }

      // Exits
      if (room.exits.length > 0) {
        const exitsHtml = room.exits.map(e =>
          '<button class="btn exit-btn" onclick="moveTo(\\'' + e.target + '\\')">' + e.direction + '</button>'
        ).join(' ');
        addSystemMsg('Exits: ' + exitsHtml);
      }

      // Update stats
      document.getElementById('stats-grid').innerHTML =
        '<div class="stat-card"><div class="stat-value">' + room.stats.total_tiles + '</div><div class="stat-label">Tiles</div></div>' +
        '<div class="stat-card"><div class="stat-value">' + room.stats.sources + '</div><div class="stat-label">Sources</div></div>' +
        '<div class="stat-card"><div class="stat-value">' + room.stats.total_feedback_positive + '</div><div class="stat-label">👍</div></div>' +
        '<div class="stat-card"><div class="stat-value">' + room.stats.total_feedback_negative + '</div><div class="stat-label">👎</div></div>';

      loadRooms(); // Refresh active state
    }
  } catch(e) {}
}

// ── Move to room ──
async function moveTo(roomId) {
  try {
    const r = await fetch(API + '/api/move', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ session_id: sessionId, direction: '__direct__', target_room: roomId })
    });
    // The move endpoint takes direction, so we need a workaround
    // Just reload the room by setting current and calling look
  } catch(e) {}
  // Fallback: directly set room
  currentRoom = roomId;
  document.getElementById('chat-messages').innerHTML = '';
  loadRoom();
}

// ── Send message ──
async function sendMsg() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';

  addUserMsg(text);

  // Check for commands
  if (['look','l','help','h','map','tiles','stats','who'].includes(text.toLowerCase())) {
    if (text.toLowerCase() === 'look' || text.toLowerCase() === 'l') {
      document.getElementById('chat-messages').innerHTML = '';
      loadRoom();
    } else if (text.toLowerCase() === 'help') {
      addSystemMsg('Commands: <b>look</b> • <b>map</b> • <b>tiles</b> • <b>stats</b> • Type anything else to ask the NPC');
    } else if (text.toLowerCase() === 'tiles') {
      const r = await fetch(API + '/api/tiles?room_id=' + currentRoom);
      const d = await r.json();
      if (d.status === 'ok') {
        d.data.forEach(t => {
          addSystemMsg('<div class="tile-q">Q: ' + escHtml(t.question) + '</div><div class="tile-a">A: ' + escHtml(t.answer) + '</div>');
        });
      }
    } else if (text.toLowerCase() === 'stats') {
      const r = await fetch(API + '/api/stats?room_id=' + currentRoom);
      const d = await r.json();
      addSystemMsg('Tiles: ' + d.data.room.total_tiles + ' | Sources: ' + d.data.room.sources + ' | 👍 ' + d.data.room.total_feedback_positive + ' | 👎 ' + d.data.room.total_feedback_negative);
    }
    return;
  }

  // Ask NPC
  try {
    const r = await fetch(API + '/api/ask', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ session_id: sessionId, question: text })
    });
    const d = await r.json();
    if (d.status === 'ok') {
      const tierClass = d.data.tier === 'tiny' ? 'badge-tiny' : d.data.tier === 'mid' ? 'badge-mid' : 'badge-human';
      addNpcMsg('NPC', d.data.response, '<span class="badge ' + tierClass + '">' + d.data.tier + '</span>');
    } else {
      addSystemMsg('Error: ' + (d.error || 'unknown'));
    }
  } catch(e) { addSystemMsg('Connection error'); }
}

// ── Message helpers ──
function addSystemMsg(html) {
  const div = document.createElement('div');
  div.className = 'msg msg-system';
  div.innerHTML = html;
  document.getElementById('chat-messages').appendChild(div);
  scrollBottom();
}

function addUserMsg(text) {
  const div = document.createElement('div');
  div.className = 'msg msg-user';
  div.textContent = text;
  document.getElementById('chat-messages').appendChild(div);
  scrollBottom();
}

function addNpcMsg(name, text, badgeHtml) {
  const div = document.createElement('div');
  div.className = 'msg msg-npc';
  div.innerHTML = '<div class="msg-label">' + escHtml(name) + ' ' + (badgeHtml||'') + '</div>' + escHtml(text);
  document.getElementById('chat-messages').appendChild(div);
  scrollBottom();
}

function scrollBottom() {
  const el = document.getElementById('chat-messages');
  el.scrollTop = el.scrollHeight;
}

function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
</script>
</body>
</html>
"""


class WebHandler(BaseHTTPRequestHandler):
    """HTTP request handler for PLATO web UI."""

    plato: PlatoWeb = None

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_html(self, html: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def do_OPTIONS(self):
        self._send_json({})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._send_html(INDEX_HTML)
            return

        # Public API (v1)
        if path.startswith("/v1/"):
            api_key = query.get("api_key", [None])[0] or self.headers.get("Authorization", "").replace("Bearer ", "")
            result = self.plato.handle_public_api(path, "GET", query=query, api_key=api_key)
            self._send_json(result)
            return

        if path.startswith("/api/"):
            result = self.plato.handle_api(path, "GET", query=query)
            self._send_json(result)
            return

        self._send_json({"status": "error", "error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = {}
        if content_length > 0:
            raw = self.rfile.read(content_length)
            try:
                body = json.loads(raw)
            except:
                body = {}

        # Public API (v1)
        if path.startswith("/v1/"):
            api_key = body.get("api_key") or self.headers.get("Authorization", "").replace("Bearer ", "")
            result = self.plato.handle_public_api(path, "POST", body=body, api_key=api_key)
            self._send_json(result)
            return

        if path.startswith("/api/"):
            result = self.plato.handle_api(path, "POST", body=body)
            self._send_json(result)
            return

        self._send_json({"status": "error", "error": "Not found"}, 404)


def run_web(config: dict):
    """Start the PLATO web server."""
    host = config.get("web_host", "0.0.0.0")
    port = config.get("web_port", 8080)

    WebHandler.plato = PlatoWeb(config)
    server = HTTPServer((host, port), WebHandler)

    print(f"  Web: \033[1mhttp://{host}:{port}\033[0m")
    print(f"  API: \033[1mhttp://{host}:{port}/api/\033[0m")
    print("")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
