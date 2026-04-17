"""
PLATO Web IDE — The main browser interface.

This is not a chat app. This is an IDE for building PLATO rooms,
managing tiles, and collaborating with AI agents in real-time.

Run: python3 -m plato --web --port 8080
"""

import json, os, time, asyncio, subprocess, threading, signal
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from plato_core.rooms import RoomManager
from plato_core.tiles import TileStore, Tile
from plato_core.npc import NPCLayer
from plato_core.onboard import detect_persona, onboard_questions, process_onboarding


class PlatoIDE:
    """PLATO Integrated Development Environment."""

    def __init__(self, config: dict):
        self.config = config
        self.room_manager = RoomManager(config.get("rooms_dir"))
        self.tile_store = TileStore(config.get("tiles_dir"))
        self.npc = NPCLayer(config, self.tile_store)
        self.visitors = {}
        self.sessions = {}
        self._seed_tiles()
        self._activity_log = []
        self._telnet_log = []

    def _seed_tiles(self):
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

    def _log(self, event: str, detail: str = ""):
        entry = {"time": time.time(), "event": event, "detail": detail}
        self._activity_log.append(entry)
        if len(self._activity_log) > 500:
            self._activity_log = self._activity_log[-500:]

    def _new_session(self, session_id: str):
        self.sessions[session_id] = {
            "room": "plato_entrance",
            "created": time.time(),
            "visitor_id": session_id[:8],
            "visitor_name": f"Visitor-{session_id[:6]}"
        }
        self._log("session_start", session_id[:8])
        return self.sessions[session_id]

    def handle_api(self, path, method, body=None, query=None):
        query = query or {}
        body = body or {}

        # ── System ──
        if path == "/api/info" and method == "GET":
            rooms = self.room_manager.all_rooms()
            total_tiles = sum(self.tile_store.room_stats(rid)["total_tiles"] for rid in rooms)
            return {"status": "ok", "data": {
                "version": "0.2.0",
                "rooms": len(rooms),
                "themes": self.room_manager.themes(),
                "total_tiles": total_tiles,
                "model": self.config.get("model_name", "tile-only"),
                "active_sessions": len(self.sessions),
                "uptime": time.time()
            }}

        elif path == "/api/activity" and method == "GET":
            since = float(query.get("since", ["0"])[0])
            entries = [e for e in self._activity_log if e["time"] > since]
            return {"status": "ok", "data": entries}

        # ── Onboarding ──
        elif path == "/api/onboard" and method == "POST":
            session_id = body.get("session_id", os.urandom(8).hex())
            self._new_session(session_id)
            questions = onboard_questions()
            visible = [{"id": q["id"], "question": q["question"], "options": q.get("options", [])} for q in questions]
            return {"status": "ok", "data": {"session_id": session_id, "questions": visible}}

        elif path == "/api/onboard/submit" and method == "POST":
            session_id = body.get("session_id")
            answers = body.get("answers", {})
            if not session_id or session_id not in self.sessions:
                return {"status": "error", "error": "Invalid session"}
            answers["_persona"] = detect_persona(answers.get("purpose", ""))
            profile = process_onboarding(answers, self.room_manager)
            self.visitors[session_id] = profile
            self.sessions[session_id]["room"] = profile["starting_room"]
            self.sessions[session_id]["visitor_name"] = profile.get("visitor_name", "Visitor")
            self.sessions[session_id]["visitor_id"] = profile.get("visitor_id", session_id[:8])
            self._log("onboard", f"{profile['persona']} -> {profile['starting_room']}")
            return {"status": "ok", "data": profile}

        # ── Rooms ──
        elif path == "/api/rooms" and method == "GET":
            rooms = []
            for rid, room in self.room_manager.all_rooms().items():
                stats = self.tile_store.room_stats(rid)
                rooms.append({
                    "room_id": rid, "name": room.name, "theme": room.theme,
                    "description": room.description[:300],
                    "npc": room.npc.name if room.npc else None,
                    "exits": [{"direction": e.direction, "target": e.target_room, "description": e.description} for e in room.exits],
                    "tiles": stats["total_tiles"], "popular": stats["popular_tiles"],
                    "seed_tiles": len(room.seed_tiles) if room.seed_tiles else 0
                })
            return {"status": "ok", "data": rooms}

        elif path == "/api/rooms/map" and method == "GET":
            m = {}
            for rid, room in self.room_manager.all_rooms().items():
                m[rid] = {"name": room.name, "theme": room.theme, "exits": {e.direction: e.target_room for e in room.exits}}
            return {"status": "ok", "data": m}

        elif path == "/api/rooms/source" and method == "GET":
            room_id = query.get("room_id", [""])[0]
            if not room_id:
                return {"status": "error", "error": "room_id required"}
            # Find the source YAML file
            for theme_dir in [d for d in os.listdir(self.config.get("rooms_dir", "templates")) if os.path.isdir(os.path.join(self.config.get("rooms_dir", "templates"), d))]:
                yaml_path = os.path.join(self.config.get("rooms_dir", "templates"), theme_dir, "rooms.yaml")
                if os.path.exists(yaml_path):
                    import yaml
                    with open(yaml_path) as f:
                        data = yaml.safe_load(f)
                    if isinstance(data, dict) and room_id in data:
                        return {"status": "ok", "data": {"room_id": room_id, "yaml": data[room_id], "file": yaml_path, "theme": theme_dir}}
            return {"status": "ok", "data": {"room_id": room_id, "yaml": None, "file": None, "theme": None}}

        elif path == "/api/rooms/create" and method == "POST":
            # Create a new room
            room_data = body
            room_id = room_data.get("room_id", f"custom_{os.urandom(4).hex()}")
            theme = room_data.get("theme", "custom")
            theme_dir = os.path.join(self.config.get("rooms_dir", "templates"), theme)
            os.makedirs(theme_dir, exist_ok=True)
            yaml_path = os.path.join(theme_dir, "rooms.yaml")

            import yaml
            existing = {}
            if os.path.exists(yaml_path):
                with open(yaml_path) as f:
                    existing = yaml.safe_load(f) or {}

            existing[room_id] = {
                "room_id": room_id,
                "name": room_data.get("name", "New Room"),
                "description": room_data.get("description", ""),
                "theme": theme,
                "metadata": {"starting_room": False},
                "exits": [],
                "seed_tiles": []
            }
            if room_data.get("npc_name"):
                existing[room_id]["npc"] = {
                    "name": room_data.get("npc_name", ""),
                    "personality": room_data.get("npc_personality", ""),
                    "greeting": room_data.get("npc_greeting", ""),
                    "model_tier": "tiny"
                }
            for e in room_data.get("exits", []):
                existing[room_id].setdefault("exits", []).append({
                    "direction": e.get("direction"),
                    "target_room": e.get("target"),
                    "description": e.get("description", "")
                })
            for t in room_data.get("seed_tiles", []):
                existing[room_id].setdefault("seed_tiles", []).append(t)

            with open(yaml_path, "w") as f:
                yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)

            self.room_manager = RoomManager(self.config.get("rooms_dir"))
            self._log("room_created", f"{room_id} in {theme}")
            return {"status": "ok", "data": {"room_id": room_id, "theme": theme}}

        # ── Session ──
        elif path == "/api/look" and method == "GET":
            session_id = query.get("session_id", [None])[0]
            if not session_id or session_id not in self.sessions:
                return {"status": "error", "error": "No session"}
            room_id = self.sessions[session_id]["room"]
            room = self.room_manager.get(room_id)
            if not room:
                return {"status": "error", "error": "Room not found"}
            stats = self.tile_store.room_stats(room_id)
            return {"status": "ok", "data": {
                "room_id": room_id, "name": room.name, "description": room.description,
                "theme": room.theme,
                "npc": {"name": room.npc.name, "greeting": room.npc.greeting, "personality": room.npc.personality if room.npc else ""} if room.npc else None,
                "exits": [{"direction": e.direction, "target": e.target_room, "description": e.description} for e in room.exits],
                "stats": stats
            }}

        elif path == "/api/move" and method == "POST":
            session_id = body.get("session_id")
            target = body.get("target_room") or body.get("room_id")
            direction = body.get("direction")
            if not session_id or session_id not in self.sessions:
                return {"status": "error", "error": "No session"}
            if target:
                self.sessions[session_id]["room"] = target
            elif direction:
                current = self.sessions[session_id]["room"]
                found = self.room_manager.get_exit_target(current, direction)
                if not found:
                    return {"status": "error", "error": f"Can't go {direction}"}
                target = found
                self.sessions[session_id]["room"] = target
            room = self.room_manager.get(target)
            self._log("move", f"{session_id[:8]} -> {target}")
            return {"status": "ok", "data": {
                "room_id": target, "name": room.name, "description": room.description,
                "npc": {"name": room.npc.name, "greeting": room.npc.greeting} if room.npc else None,
                "exits": [{"direction": e.direction, "target": e.target_room, "description": e.description} for e in room.exits]
            }}

        # ── NPC ──
        elif path == "/api/ask" and method == "POST":
            session_id = body.get("session_id")
            question = body.get("question", "")
            if not session_id or session_id not in self.sessions:
                return {"status": "error", "error": "No session"}
            room_id = self.sessions[session_id]["room"]
            visitor_id = self.sessions[session_id]["visitor_id"]
            room = self.room_manager.get(room_id)
            personality = room.npc.personality if room and room.npc else ""
            result = self.npc.handle_query(room_id, visitor_id, question, personality)
            self._log("ask", f"{visitor_id} in {room_id}: {question[:60]}")
            return {"status": "ok", "data": result}

        # ── Tiles ──
        elif path == "/api/tiles" and method == "GET":
            room_id = query.get("room_id", [None])[0]
            limit = int(query.get("limit", ["50"])[0])
            if not room_id:
                return {"status": "error", "error": "room_id required"}
            tiles = self.tile_store.all_tiles(room_id)[-limit:]
            return {"status": "ok", "data": [
                {"tile_id": t.tile_id, "question": t.question, "answer": t.answer,
                 "source": t.source, "score": t.score, "tags": t.tags,
                 "feedback_positive": t.feedback_positive, "feedback_negative": t.feedback_negative,
                 "created": t.created if isinstance(t.created, str) else str(t.created)}
                for t in reversed(tiles)
            ]}

        elif path == "/api/tiles" and method == "POST":
            session_id = body.get("session_id")
            question = body.get("question", "")
            answer = body.get("answer", "")
            tags = body.get("tags", [])
            room_id = body.get("room_id")
            if not question or not answer:
                return {"status": "error", "error": "Question and answer required"}
            if not session_id or session_id not in self.sessions:
                return {"status": "error", "error": "No session"}
            target_room = room_id or self.sessions[session_id]["room"]
            visitor_id = self.sessions[session_id]["visitor_id"]
            tile = Tile(room_id=target_room, question=question, answer=answer,
                       source=visitor_id, tags=tags, context="Added via PLATO IDE")
            tile_id = self.tile_store.add(tile)
            self._log("tile_added", f"{tile_id}: {question[:40]}")
            return {"status": "ok", "data": {"tile_id": tile_id}}

        elif path == "/api/tiles/delete" and method == "POST":
            tile_id = body.get("tile_id")
            room_id = body.get("room_id")
            if not tile_id or not room_id:
                return {"status": "error", "error": "tile_id and room_id required"}
            tiles = self.tile_store.all_tiles(room_id)
            new_tiles = [t for t in tiles if t.tile_id != tile_id]
            if len(new_tiles) == len(tiles):
                return {"status": "error", "error": "Tile not found"}
            # Rewrite the room file
            import yaml
            path = os.path.join(self.tile_store.tiles_dir, f"{room_id}.json")
            with open(path, "w") as f:
                json.dump([{"tile_id": t.tile_id, "room_id": t.room_id, "question": t.question,
                            "answer": t.answer, "source": t.source, "tags": t.tags,
                            "context": getattr(t, 'context', ''),
                            "score": t.score, "feedback_positive": t.feedback_positive,
                            "feedback_negative": t.feedback_negative,
                            "created": t.created if isinstance(t.created, str) else str(t.created)}
                           for t in new_tiles], f, indent=2, default=str)
            self._log("tile_deleted", f"{tile_id} from {room_id}")
            return {"status": "ok", "data": {"deleted": tile_id}}

        elif path == "/api/feedback" and method == "POST":
            tile_id = body.get("tile_id")
            room_id = body.get("room_id")
            positive = body.get("positive", True)
            if not tile_id or not room_id:
                return {"status": "error", "error": "tile_id and room_id required"}
            tiles = self.tile_store.all_tiles(room_id)
            for t in tiles:
                if t.tile_id == tile_id:
                    t.record_feedback(positive)
                    break
            self._log("feedback", f"{tile_id}: {'👍' if positive else '👎'}")
            return {"status": "ok", "data": {"tile_id": tile_id}}

        elif path == "/api/search" and method == "GET":
            room_id = query.get("room_id", [None])[0]
            q = query.get("q", [""])[0]
            if not room_id or not q:
                return {"status": "error", "error": "room_id and q required"}
            results = self.tile_store.search(room_id, q, limit=20)
            return {"status": "ok", "data": [{"tile_id": t.tile_id, "question": t.question, "answer": t.answer[:200], "score": t.score} for t in results]}

        # ── Stats ──
        elif path == "/api/stats" and method == "GET":
            room_id = query.get("room_id", [None])[0]
            if room_id:
                return {"status": "ok", "data": {"room": self.tile_store.room_stats(room_id), "npc": self.npc.get_stats()}}
            all_stats = {rid: self.tile_store.room_stats(rid) for rid in self.room_manager.all_rooms()}
            return {"status": "ok", "data": {"rooms": all_stats, "npc": self.npc.get_stats()}}

        # ── Export ──
        elif path == "/api/export" and method == "GET":
            room_id = query.get("room_id", [None])[0]
            fmt = query.get("format", ["instruction-input-output"])[0]
            entries = self.tile_store.export_for_lora(room_id)
            return {"status": "ok", "data": {"count": len(entries), "format": fmt, "entries": entries[:100]}}

        elif path == "/api/workspace/download" and method == "GET":
            """Export entire workspace as downloadable zip."""
            import zipfile, io, shutil
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Tile data
                tiles_dir = self.tile_store.tiles_dir
                if os.path.exists(tiles_dir):
                    for f in os.listdir(tiles_dir):
                        if f.endswith('.json'):
                            zf.write(os.path.join(tiles_dir, f), f"data/tiles/{f}")
                # Room templates
                rooms_dir = self.config.get("rooms_dir", "templates")
                if os.path.exists(rooms_dir):
                    for root, dirs, files in os.walk(rooms_dir):
                        for f in files:
                            full = os.path.join(root, f)
                            arc = os.path.join("templates", os.path.relpath(full, rooms_dir))
                            zf.write(full, arc)
                # Activity log
                zf.writestr("data/activity.json", json.dumps(self._activity_log, indent=2, default=str))
                # Export config
                export_config = {
                    "version": "0.2.0",
                    "exported": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "total_tiles": sum(self.tile_store.room_stats(rid)["total_tiles"] for rid in self.room_manager.all_rooms()),
                    "rooms": len(self.room_manager.all_rooms()),
                    "themes": self.room_manager.themes()
                }
                zf.writestr("data/export.json", json.dumps(export_config, indent=2))

            buf.seek(0)
            return {"status": "ok", "data": {"type": "zip", "size": len(buf.getvalue())}, "_zip_buffer": buf}

        elif path == "/api/workspace/upload" and method == "POST":
            """Import tiles from uploaded workspace."""
            # Handled in do_POST with multipart
            return {"status": "error", "error": "Use multipart upload"}

        elif path == "/api/workspace/merge-ready" and method == "GET":
            """Get tiles ready for global merge."""
            entries = self.tile_store.export_for_lora()
            export_config = {
                "version": "0.2.0",
                "source": "plato-workspace-export",
                "exported": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "count": len(entries),
                "rooms": list(set(t.get("room_id", "unknown") for t in entries))
            }
            return {"status": "ok", "data": {"config": export_config, "count": len(entries), "entries": entries, "download_url": "/api/workspace/merge-download"}}

        elif path == "/api/workspace/merge-download" and method == "GET":
            entries = self.tile_store.export_for_lora()
            import io
            buf = io.BytesIO()
            buf.write(json.dumps({
                "version": "0.2.0",
                "format": "instruction-input-output",
                "exported": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "count": len(entries),
                "entries": entries
            }, indent=2).encode())
            buf.seek(0)
            return {"status": "ok", "data": {"type": "json", "size": len(buf.getvalue())}, "_json_buffer": buf}

        elif path == "/api/agents/status" and method == "GET":
            """Show which agents are connected (session activity)."""
            active = []
            for sid, sess in self.sessions.items():
                age = time.time() - sess["created"]
                if age < 3600:  # Active in last hour
                    active.append({
                        "visitor_id": sess["visitor_id"],
                        "name": sess.get("visitor_name", "Unknown"),
                        "room": sess["room"],
                        "age_seconds": int(age)
                    })
            return {"status": "ok", "data": {"total": len(self.sessions), "active": active}}

        return {"status": "error", "error": f"Unknown: {method} {path}"}


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PLATO IDE</title>
<style>
:root{--bg:#08080d;--surface:#10101a;--border:#1e1e3a;--text:#e0e0e8;--dim:#5a5a7a;--accent:#8be9fd;--green:#50fa7b;--yellow:#f1fa8c;--pink:#ff79c6;--orange:#ffb86c;--red:#ff5555;--purple:#bd93f9}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'SF Mono','Fira Code','Cascadia Code',monospace;background:var(--bg);color:var(--text);height:100vh;overflow:hidden;font-size:13px;line-height:1.5}
::selection{background:var(--accent);color:var(--bg)}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

/* ── Layout ── */
.app{display:grid;grid-template-rows:36px 1fr 24px;grid-template-columns:240px 1fr 320px;height:100vh}
.topbar{grid-column:1/-1;background:var(--surface);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 12px;gap:12px;z-index:10}
.topbar .logo{color:var(--accent);font-weight:700;font-size:14px;letter-spacing:1px}
.topbar .sep{color:var(--border)}
.topbar .room-name{color:var(--text);font-weight:600}
.topbar .room-theme{color:var(--dim);font-size:11px;background:var(--bg);padding:1px 6px;border-radius:8px}
.topbar .spacer{flex:1}
.topbar .agents{color:var(--green);font-size:11px}
.topbar .agents .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--green);margin-right:4px}
.bottombar{grid-column:1/-1;background:var(--surface);border-top:1px solid var(--border);padding:0 12px;display:flex;align-items:center;gap:16px;font-size:11px;color:var(--dim)}

/* ── Sidebar ── */
.sidebar{background:var(--surface);border-right:1px solid var(--border);overflow-y:auto;display:flex;flex-direction:column}
.sidebar-header{padding:8px 10px;font-size:10px;text-transform:uppercase;letter-spacing:1.5px;color:var(--dim);border-bottom:1px solid var(--border)}
.room-item{padding:6px 10px;cursor:pointer;border-left:2px solid transparent;transition:all .15s;display:flex;justify-content:space-between;align-items:center}
.room-item:hover{background:rgba(139,233,253,.05)}
.room-item.active{background:rgba(139,233,253,.08);border-left-color:var(--accent)}
.room-item .name{font-size:12px;color:var(--text)}
.room-item .count{font-size:10px;color:var(--dim);background:var(--bg);padding:0 5px;border-radius:8px}
.theme-group{border-bottom:1px solid var(--border)}
.theme-label{padding:4px 10px;font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:1px}

/* ── Main Panel ── */
.main{display:flex;flex-direction:column;overflow:hidden;position:relative}
.main-header{padding:8px 12px;border-bottom:1px solid var(--border);background:var(--surface);font-size:11px;color:var(--dim);display:flex;align-items:center;gap:8px}
.main-header .tab{padding:3px 10px;border-radius:4px;cursor:pointer;color:var(--dim);transition:all .15s}
.main-header .tab:hover{color:var(--text)}
.main-header .tab.active{color:var(--accent);background:rgba(139,233,253,.1)}

/* ── Chat ── */
.chat{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px}
.msg{max-width:88%;padding:8px 12px;border-radius:8px;font-size:12.5px;line-height:1.6;word-wrap:break-word}
.msg-sys{background:var(--surface);border:1px solid var(--border);color:var(--accent);align-self:center;font-size:11px;padding:4px 12px;border-radius:20px}
.msg-npc{background:#0f1a2a;border:1px solid #1a2a3a;align-self:flex-start}
.msg-npc .label{color:var(--orange);font-weight:700;font-size:10px;margin-bottom:2px}
.msg-npc .tier{color:var(--dim);font-size:9px;margin-left:6px}
.msg-user{background:#1a1a2a;border:1px solid #2a2a3a;align-self:flex-end;color:var(--text)}
.msg-cmd{background:#0a1a0a;border:1px solid #1a2a1a;align-self:flex-start;font-size:11px;color:var(--green);font-family:inherit;white-space:pre-wrap}
.chat-input{padding:8px;border-top:1px solid var(--border);display:flex;gap:8px;background:var(--surface)}
.chat-input input{flex:1;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:6px 10px;border-radius:6px;font-family:inherit;font-size:12px}
.chat-input input:focus{outline:none;border-color:var(--accent)}
.chat-input .btn{padding:6px 14px;border-radius:6px;cursor:pointer;font-size:11px;font-weight:600;border:1px solid var(--accent);background:rgba(139,233,253,.1);color:var(--accent);transition:all .15s;font-family:inherit}
.chat-input .btn:hover{background:rgba(139,233,253,.2)}
.chat-input .btn-send{background:var(--accent);color:var(--bg);border-color:var(--accent)}

/* ── Right Panel ── */
.right{background:var(--surface);border-left:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.panel-tabs{display:flex;border-bottom:1px solid var(--border)}
.panel-tabs .ptab{flex:1;padding:7px;text-align:center;font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);cursor:pointer;border-bottom:2px solid transparent;transition:all .15s}
.panel-tabs .ptab:hover{color:var(--text)}
.panel-tabs .ptab.active{color:var(--accent);border-bottom-color:var(--accent)}
.panel-content{flex:1;overflow-y:auto;padding:8px}
.tile-card{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px;margin-bottom:6px;transition:all .15s}
.tile-card:hover{border-color:var(--accent)}
.tile-card .q{color:var(--yellow);font-size:11px;font-weight:600;margin-bottom:3px}
.tile-card .a{color:var(--text);font-size:11px;line-height:1.5}
.tile-card .meta{margin-top:4px;display:flex;gap:8px;font-size:9px;color:var(--dim)}
.tile-card .meta .score{color:var(--green)}
.tile-card .actions{margin-top:4px;display:flex;gap:4px}
.btn-xs{padding:2px 6px;border-radius:3px;font-size:9px;cursor:pointer;border:1px solid var(--border);background:transparent;color:var(--dim);font-family:inherit}
.btn-xs:hover{border-color:var(--accent);color:var(--accent)}
.btn-xs.pos:hover{border-color:var(--green);color:var(--green)}
.btn-xs.neg:hover{border-color:var(--red);color:var(--red)}

/* ── Onboarding ── */
.onboard{display:flex;align-items:center;justify-content:center;height:100%;background:var(--bg)}
.onboard .card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:32px;max-width:460px;width:90%}
.onboard h2{color:var(--accent);margin-bottom:4px;font-size:18px;letter-spacing:2px}
.onboard .sub{color:var(--dim);margin-bottom:24px;font-size:12px}
.field{margin-bottom:14px}
.field label{display:block;color:var(--text);margin-bottom:4px;font-size:11px}
.field input,.field textarea{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:8px;border-radius:6px;font-family:inherit;font-size:12px;resize:vertical}
.field input:focus,.field textarea:focus{outline:none;border-color:var(--accent)}
.field .hint{color:var(--dim);font-size:10px;margin-top:3px}
.btn-primary{width:100%;padding:10px;border:1px solid var(--accent);background:rgba(139,233,253,.12);color:var(--accent);border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;font-family:inherit;letter-spacing:1px;transition:all .15s}
.btn-primary:hover{background:rgba(139,233,253,.22)}

/* ── Room Editor ── */
.editor{display:none;flex-direction:column;height:100%}
.editor.active{display:flex}
.editor textarea{flex:1;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:10px;font-family:inherit;font-size:11px;resize:none;line-height:1.6}
.editor textarea:focus{outline:none;border-color:var(--accent)}
.editor-bar{display:flex;gap:6px;padding:6px;border-top:1px solid var(--border);background:var(--surface)}

.hidden{display:none!important}
</style>
</head>
<body>

<!-- Onboarding -->
<div id="onboard" class="onboard">
<div class="card">
<h2>&#x26A1; PLATO</h2>
<p class="sub">Git-Agent Maintenance Mode &mdash; v0.2.0</p>
<div id="ob-form">
  <div class="field"><label>Your name</label><input id="ob-name" placeholder="What should we call you?" autofocus></div>
  <div class="field"><label>What brings you here?</label><textarea id="ob-purpose" rows="2" placeholder="I'm building a... / I need help with..."></textarea><div class="hint">This places you in the right room</div></div>
  <div class="field"><label>Experience</label><input id="ob-exp" placeholder="First time / Experienced / Expert"></div>
  <div class="field"><label>API endpoint <span style="color:var(--dim)">(optional)</span></label><input id="ob-model" placeholder="https://api.deepseek.com/v1/chat/completions"><div class="hint">Leave blank for tile-only mode. Claude Code / aider / OpenClaw can board via telnet on port 4040.</div></div>
  <button class="btn-primary" onclick="submitOnboard()">Enter PLATO &rarr;</button>
</div>
</div>
</div>

<!-- IDE -->
<div id="ide" class="app hidden">
  <!-- Top Bar -->
  <div class="topbar">
    <span class="logo">&copy; PLATO</span>
    <span class="sep">/</span>
    <span class="room-name" id="top-room">Loading...</span>
    <span class="room-theme" id="top-theme"></span>
    <div class="spacer"></div>
    <div class="agents" id="top-agents"></div>
    <button class="btn-xs" onclick="downloadWorkspace()" title="Download workspace">&darr; Export</button>
    <button class="btn-xs" onclick="window.open('/api/workspace/merge-ready','_blank')" title="Export for global merge">&#x2B06; Merge</button>
  </div>

  <!-- Sidebar -->
  <div class="sidebar">
    <div class="sidebar-header">Rooms</div>
    <div id="room-list" style="flex:1;overflow-y:auto"></div>
    <div style="padding:8px;border-top:1px solid var(--border)">
      <button class="btn-xs" style="width:100%;padding:5px" onclick="showNewRoom()">+ New Room</button>
    </div>
  </div>

  <!-- Main -->
  <div class="main" id="main-panel">
    <div class="main-header">
      <span class="tab active" onclick="switchTab('chat',this)">Chat</span>
      <span class="tab" onclick="switchTab('editor',this)">Room YAML</span>
      <span class="tab" onclick="switchTab('agents',this)">Agents</span>
    </div>
    <div class="chat" id="chat-panel"></div>
    <div class="editor" id="editor-panel">
      <textarea id="room-yaml" spellcheck="false" placeholder="Room YAML will load here..."></textarea>
      <div class="editor-bar">
        <button class="btn-xs" onclick="loadRoomYaml()">Refresh</button>
        <button class="btn-xs" style="color:var(--green);border-color:var(--green)" onclick="saveRoomYaml()">Save & Reload</button>
        <span style="flex:1"></span>
        <span style="font-size:10px;color:var(--dim)">Edit room definition, then save.</span>
      </div>
    </div>
    <div class="chat hidden" id="agents-panel">
      <div style="text-align:center;padding:20px;color:var(--dim)">
        <p style="margin-bottom:12px"><strong style="color:var(--text)">Boarding Instructions</strong></p>
        <p>PLATO runs a telnet server on <strong style="color:var(--accent)">port 4040</strong>.</p>
        <br>
        <p>AI agents can board via telnet:</p>
        <pre style="text-align:left;background:var(--bg);padding:10px;border-radius:6px;margin:8px 0;color:var(--green);font-size:11px">claude --print "Connect to PLATO on localhost:4040<br>and help me world-build rooms"

aider --msg "Connect to PLATO at telnet localhost 4040<br>and add tiles to the current room"

# OpenClaw connects natively via telnet</pre>
        <br>
        <p>The agent sees the same room, the same tiles, the same NPC.</p>
        <p>They can add tiles, create rooms, ask questions &mdash; alongside you.</p>
        <br>
        <p style="color:var(--yellow)">Your experience is preserved whether or not we merge it globally.</p>
        <button class="btn-xs" onclick="refreshAgents()" style="margin-top:8px">Refresh Agent Status</button>
      </div>
    </div>
    <div class="chat-input">
      <input id="chat-in" placeholder="Ask, navigate, or type a command..." onkeydown="if(event.key==='Enter')send()">
      <button class="btn" onclick="showNewTile()">+ Tile</button>
      <button class="btn btn-send" onclick="send()">Send</button>
    </div>
  </div>

  <!-- Right Panel -->
  <div class="right">
    <div class="panel-tabs">
      <div class="ptab active" onclick="switchRight('tiles',this)">Tiles</div>
      <div class="ptab" onclick="switchRight('map',this)">Map</div>
      <div class="ptab" onclick="switchRight('stats',this)">Stats</div>
    </div>
    <div class="panel-content" id="tiles-panel"></div>
    <div class="panel-content hidden" id="map-panel"></div>
    <div class="panel-content hidden" id="stats-panel"></div>
  </div>

  <!-- Bottom Bar -->
  <div class="bottombar">
    <span id="status-rooms">0 rooms</span>
    <span id="status-tiles">0 tiles</span>
    <span id="status-model">tile-only</span>
    <div style="flex:1"></div>
    <span>telnet :4040 &bull; web :8080</span>
  </div>
</div>

<script>
const A='';let sid=null,curRoom=null,lastActivity=0;

async function api(path,opts={}){
  const r=await fetch(A+path,{headers:{'Content-Type':'application/json'},...opts});
  return r.json();
}

async function submitOnboard(){
  const n=$('ob-name').value||'Visitor';
  const p=$('ob-purpose').value||'exploring';
  const e=$('ob-exp').value||'first time';
  const m=$('ob-model').value.trim();
  let s;
  try{s=(await api('/api/onboard',{method:'POST',body:JSON.stringify({})})).data.session_id;}catch(e){s=crypto.randomUUID();}
  const r=await api('/api/onboard/submit',{method:'POST',body:JSON.stringify({session_id:s,answers:{name:n,purpose:p,experience:e,model_endpoint:m}})});
  if(r.status==='ok'){sid=s;curRoom=r.data.starting_room;$('onboard').classList.add('hidden');$('ide').classList.remove('hidden');sysMsg(r.data.greeting);loadAll();}else{alert(r.error);}
}

function sysMsg(html){addMsg('msg-sys',html);}
function npcMsg(name,text,tier){addMsg('msg-npc',`<span class="label">${esc(name)} <span class="tier">${tier||''}</span></span>${esc(text)}`);}
function userMsg(text){addMsg('msg-user',esc(text));}
function cmdMsg(text){addMsg('msg-cmd',esc(text));}
function addMsg(cls,html){const d=document.createElement('div');d.className='msg '+cls;d.innerHTML=html;$('chat-panel').appendChild(d);$('chat-panel').scrollTop=1e9;}

async function loadAll(){loadRooms();loadRoom();loadTiles();loadStats();refreshInfo();}

async function refreshInfo(){
  const r=await api('/api/info');
  $('status-rooms').textContent=r.data.rooms+' rooms';
  $('status-tiles').textContent=r.data.total_tiles+' tiles';
  $('status-model').textContent=r.data.model||'tile-only';
}

async function loadRooms(){
  const r=await api('/api/rooms');
  const list=$('room-list');list.innerHTML='';
  const themes={};
  r.data.forEach(rm=>{(themes[rm.theme]=themes[rm.theme]||[]).push(rm);});
  Object.keys(themes).sort().forEach(t=>{
    const g=document.createElement('div');g.className='theme-group';
    const l=document.createElement('div');l.className='theme-label';l.textContent=t;g.appendChild(l);
    themes[t].forEach(rm=>{
      const d=document.createElement('div');d.className='room-item'+(rm.room_id===curRoom?' active':'');
      d.innerHTML=`<span class="name">${esc(rm.name)}</span><span class="count">${rm.tiles}</span>`;
      d.onclick=()=>goRoom(rm.room_id);g.appendChild(d);
    });list.appendChild(g);
  });
}

async function loadRoom(){
  if(!sid)return;
  const r=await api('/api/look?session_id='+sid);
  if(r.status!=='ok')return;
  const d=r.data;curRoom=d.room_id;
  $('top-room').textContent=d.name;
  $('top-theme').textContent=d.theme;
  if(d.npc)npcMsg(d.npc.name,d.npc.greeting,'');
  if(d.exits.length){
    const ex=d.exits.map(e=>`<span class="btn-xs" onclick="goRoom('${e.target_room}')" style="margin:2px">${e.direction}</span>`).join('');
    sysMsg('Exits: '+ex);
  }
}

async function goRoom(id){
  $('chat-panel').innerHTML='';
  await api('/api/move',{method:'POST',body:JSON.stringify({session_id:sid,target_room:id})});
  loadRoom();loadTiles();loadRooms();
}

async function loadTiles(){
  if(!curRoom)return;
  const r=await api('/api/tiles?room_id='+curRoom+'&limit=50');
  const p=$('tiles-panel');p.innerHTML='';
  if(!r.data.length){p.innerHTML='<div style="text-align:center;padding:20px;color:var(--dim);font-size:11px">No tiles yet.<br><br>Ask the NPC a question, or add a tile manually.</div>';return;}
  r.data.forEach(t=>{
    const c=document.createElement('div');c.className='tile-card';
    c.innerHTML=`<div class="q">${esc(t.question)}</div><div class="a">${esc(t.answer||'').substring(0,150)}${(t.answer||'').length>150?'...':''}</div><div class="meta"><span class="score">${t.score.toFixed(2)}</span><span>👍${t.feedback_positive||0}</span><span>👎${t.feedback_negative||0}</span><span>${t.source||'?'}</span></div><div class="actions"><button class="btn-xs pos" onclick="feedback('${curRoom}','${t.tile_id}',true)">👍</button><button class="btn-xs neg" onclick="feedback('${curRoom}','${t.tile_id}',false)">👎</button></div>`;
    p.appendChild(c);
  });
}

async function loadStats(){
  const r=await api('/api/stats');
  const p=$('stats-panel');
  let h='<div style="font-size:11px">';
  if(r.data.rooms){
    const rooms=Object.entries(r.data.rooms);
    rooms.sort((a,b)=>b[1].total_tiles-a[1].total_tiles);
    h+='<div style="font-weight:700;color:var(--accent);margin-bottom:8px">Room Tile Counts</div>';
    rooms.forEach(([id,s])=>{h+=`<div style="display:flex;justify-content:space-between;padding:2px 0"><span>${id}</span><span>${s.total_tiles} tiles | 👍${s.total_feedback_positive} 👎${s.total_feedback_negative}</span></div>`;});
  }
  if(r.data.npc){
    h+='<div style="font-weight:700;color:var(--accent);margin:12px 0 8px">NPC Layer</div>';
    h+=`<div>Queries: ${r.data.npc.total_queries}</div>`;
    h+=`<div>Tiny hits: ${r.data.npc.tiny_hits} (${(r.data.npc.tiny_rate*100).toFixed(0)}%)</div>`;
    h+=`<div>Mid-tier: ${r.data.npc.mid_hits} (${(r.data.npc.mid_rate*100).toFixed(0)}%)</div>`;
    h+=`<div>Escalations: ${r.data.npc.human_escapes}</div>`;
  }
  h+='</div>';p.innerHTML=h;
}

async function loadMap(){
  const r=await api('/api/rooms/map');
  const p=$('map-panel');let h='<div style="font-size:11px">';
  Object.entries(r.data).forEach(([id,rm])=>{
    h+=`<div style="margin-bottom:6px"><strong style="color:var(--accent)">${rm.name}</strong><span style="color:var(--dim);margin-left:6px;font-size:10px">[${rm.theme}]</span><div style="color:var(--dim);margin-top:2px">${Object.entries(rm.exits).map(([d,t])=>`<span class="btn-xs" onclick="goRoom('${t}')" style="margin:1px">${d}&rarr;${t.split('_').pop()}</span>`).join('')}</div></div>`;
  });
  h+='</div>';p.innerHTML=h;
}

async function send(){
  const inp=$('chat-in');const t=inp.value.trim();if(!t)return;inp.value='';userMsg(t);
  const cmd=t.toLowerCase();
  if(cmd==='look'||cmd==='l'){$('chat-panel').innerHTML='';loadRoom();return;}
  if(cmd==='help'){sysMsg('<b>Commands:</b> look, help, map, tiles, stats, who<br><b>Navigate:</b> click exits or type direction<br><b>Ask:</b> type anything else');return;}
  if(cmd==='map'){switchRight('map',document.querySelector('.panel-tabs .ptab:nth-child(2)'));return;}
  if(cmd==='tiles'){switchRight('tiles',document.querySelector('.panel-tabs .ptab:first-child'));return;}
  if(cmd==='stats'){switchRight('stats',document.querySelector('.panel-tabs .ptab:last-child'));return;}
  if(cmd==='who'){refreshAgents();return;}
  const r=await api('/api/ask',{method:'POST',body:JSON.stringify({session_id:sid,question:t})});
  if(r.status==='ok'){const badge=r.data.tier==='tiny'?'<span style="color:var(--green)">tile</span>':r.data.tier==='mid'?'<span style="color:var(--yellow)">synth</span>':'<span style="color:var(--pink)">human</span>';npcMsg('NPC',r.data.response,badge);if(r.data.new_tile_created)sysMsg('New tile created from this interaction');}
  else sysMsg('Error: '+(r.error||'?'));
}

async function feedback(room,tid,pos){
  await api('/api/feedback',{method:'POST',body:JSON.stringify({room_id:room,tile_id:tid,positive:pos})});
  loadTiles();sysMsg(pos?'👍 Marked helpful':'👎 Marked unhelpful');
}

function showNewTile(){
  const q=prompt('Question (tile prompt):');if(!q)return;
  const a=prompt('Answer:');if(!a)return;
  const tags=prompt('Tags (comma-separated, optional):','');
  api('/api/tiles',{method:'POST',body:JSON.stringify({session_id:sid,question:q,answer:a,tags:tags?tags.split(',').map(t=>t.trim()):[]})}).then(()=>{loadTiles();sysMsg('Tile added');});
}

function showNewRoom(){
  const name=prompt('Room name:');if(!name)return;
  const id=name.toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/_+$/,'');
  const desc=prompt('Description:')||'';
  const npc=prompt('NPC name (optional):')||'';
  const greeting=prompt('NPC greeting (optional):')||'';
  const theme=prompt('Theme (optional):')||'custom';
  const exits_str=prompt('Exits (comma-separated directions, optional):')||'';
  const exits=exits_str.split(',').filter(Boolean).map(d=>({direction:d.trim(),target:'plato_entrance',description:'Back to entrance'}));
  api('/api/rooms/create',{method:'POST',body:JSON.stringify({room_id:id,name,description:desc,theme,npc_name:npc,npc_greeting:greeting,exits})}).then(r=>{if(r.status==='ok'){loadAll();sysMsg('Room created: '+name);}else alert(r.error);});
}

function switchTab(tab,el){
  document.querySelectorAll('.main-header .tab').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
  $('chat-panel').classList.toggle('hidden',tab!=='chat');
  $('editor-panel').classList.toggle('active',tab==='editor');
  $('agents-panel').classList.toggle('hidden',tab!=='agents');
  if(tab==='editor')loadRoomYaml();
  if(tab==='agents')refreshAgents();
}

function switchRight(panel,el){
  document.querySelectorAll('.panel-tabs .ptab').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
  $('tiles-panel').classList.toggle('hidden',panel!=='tiles');
  $('map-panel').classList.toggle('hidden',panel!=='map');
  $('stats-panel').classList.toggle('hidden',panel!=='stats');
  if(panel==='map')loadMap();
  if(panel==='stats')loadStats();
}

async function loadRoomYaml(){
  const r=await api('/api/rooms/source?room_id='+curRoom);
  if(r.data.yaml)$('room-yaml').value=JSON.stringify(r.data.yaml,null,2);
  else $('room-yaml').value='# Room definition not found in templates\n# This room may be runtime-generated.';
}

async function saveRoomYaml(){
  sysMsg('Saving room definition...');
  // For now, this shows the YAML. Full save requires server-side write support.
  sysMsg('Room definitions are in templates/<theme>/rooms.yaml.<br>Edit the file directly in the Codespace editor, then reload.');
}

async function refreshAgents(){
  const r=await api('/api/agents/status');
  const el=$('top-agents');
  el.innerHTML=r.data.active.length?`<span class="dot"></span>${r.data.active.length} agent${r.data.active.length>1?'s':''} aboard`:''+$('top-agents').innerHTML.replace(/<span class="dot">.*?<\/span>/,'');
}

async function downloadWorkspace(){
  sysMsg('Preparing workspace download...');
  // Use merge-download as the zip isn't easily handled via fetch
  const r=await api('/api/workspace/merge-ready');
  if(r.status==='ok'){
    const blob=new Blob([JSON.stringify(r.data,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');a.href=url;a.download=`plato-workspace-${new Date().toISOString().slice(0,10)}.json`;a.click();
    URL.revokeObjectURL(url);
    sysMsg('Workspace exported! Contains all your tiles and room definitions.');
  }
}

function esc(s){const d=document.createElement('div');d.textContent=s||'';return d.innerHTML;}
function $(id){return document.getElementById(id);}

// Auto-refresh every 30s
setInterval(()=>{if(sid)refreshAgents();},30000);
</script>
</body>
</html>
"""


class IDEHandler(BaseHTTPRequestHandler):
    plato: PlatoIDE = None

    def log_message(self, *a): pass

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html;charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def _download(self, buf, filename, content_type="application/octet-stream"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(buf.read() if hasattr(buf, 'read') else buf)

    def do_OPTIONS(self): self._json({})

    def do_GET(self):
        p = urlparse(self.path).path
        q = parse_qs(urlparse(self.path).query)
        if p in ("/", "/index.html"): self._html(INDEX_HTML); return
        if p == "/api/workspace/download":
            r = self.plato.handle_api("/api/workspace/download", "GET", query=q)
            if r.get("_zip_buffer"):
                self._download(r["_zip_buffer"], f"plato-workspace-{time.strftime('%Y%m%d')}.zip", "application/zip")
            else: self._json(r)
            return
        if p == "/api/workspace/merge-download":
            r = self.plato.handle_api("/api/workspace/merge-download", "GET", query=q)
            if r.get("_json_buffer"):
                self._download(r["_json_buffer"], f"plato-merge-{time.strftime('%Y%m%d')}.json", "application/json")
            else: self._json(r)
            return
        if p.startswith("/api/"): self._json(self.plato.handle_api(p, "GET", query=q)); return
        self._json({"status": "error", "error": "Not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path).path
        cl = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(cl)) if cl > 0 else {}
        if p.startswith("/api/"): self._json(self.plato.handle_api(p, "POST", body=body)); return
        self._json({"status": "error", "error": "Not found"}, 404)


def run_ide(config: dict):
    host = config.get("web_host", "0.0.0.0")
    port = config.get("web_port", 8080)
    IDEHandler.plato = PlatoIDE(config)
    server = HTTPServer((host, port), IDEHandler)
    print(f"  Web IDE: \033[1;32mhttp://{host}:{port}\033[0m")
    print(f"  API:     \033[1mhttp://{host}:{port}/api/\033[0m")
    print("")
    try: server.serve_forever()
    except KeyboardInterrupt: server.shutdown()
