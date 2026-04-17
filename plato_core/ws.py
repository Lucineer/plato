"""
PLATO WebSocket Server — Real-time multi-visitor interaction.

Visitors see each other's messages in real-time. Agents boarding via telnet
broadcast their presence. Everything is evented.

Runs alongside the HTTP IDE on the same port.
"""

import json, os, time, asyncio, hashlib
from typing import Dict, Set
from plato_core.rooms import RoomManager
from plato_core.tiles import TileStore
from plato_core.npc import NPCLayer


class WSClient:
    """A connected WebSocket client."""

    def __init__(self, ws, session_id: str, visitor_id: str, visitor_name: str):
        self.ws = ws
        self.session_id = session_id
        self.visitor_id = visitor_id
        self.visitor_name = visitor_name
        self.room_id = "plato_entrance"
        self.connected = time.time()
        self.last_heartbeat = time.time()

    def to_dict(self):
        return {
            "visitor_id": self.visitor_id,
            "visitor_name": self.visitor_name,
            "room": self.room_id,
            "connected_since": self.connected,
            "age_seconds": int(time.time() - self.connected)
        }


class PlatoWS:
    """WebSocket server for real-time PLATO interaction."""

    def __init__(self, ide):
        self.ide = ide  # PlatoIDE instance
        self.clients: Dict[str, WSClient] = {}
        self._handlers = {}

    def on(self, event: str, handler):
        """Register an event handler."""
        self._handlers[event] = handler

    async def handle_client(self, websocket, path=None):
        """Handle a new WebSocket connection."""
        client = None
        try:
            # Wait for auth message
            auth_msg = await asyncio.wait_for(websocket.recv(), timeout=10)
            auth = json.loads(auth_msg)

            session_id = auth.get("session_id")
            if not session_id or session_id not in self.ide.sessions:
                await websocket.send(json.dumps({"type": "error", "error": "Invalid session. Refresh the page."}))
                await websocket.close()
                return

            session = self.ide.sessions[session_id]
            client = WSClient(
                ws=websocket,
                session_id=session_id,
                visitor_id=session["visitor_id"],
                visitor_name=session.get("visitor_name", "Visitor")
            )
            client.room_id = session["room"]
            self.clients[session_id] = client

            # Send initial state
            room = self.ide.room_manager.get(client.room_id)
            await self._send(client, {
                "type": "connected",
                "room": client.room_id,
                "room_name": room.name if room else "Unknown",
                "visitors": [c.to_dict() for c in self.clients.values()]
            })

            # Broadcast arrival
            await self._broadcast_room(client.room_id, {
                "type": "visitor_arrived",
                "visitor": client.to_dict()
            }, exclude=client.session_id)

            # Message loop
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                    await self._handle_message(client, msg)
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    await self._send(client, {"type": "error", "error": str(e)})

        except asyncio.TimeoutError:
            pass
        except Exception:
            pass
        finally:
            if client:
                self.clients.pop(client.session_id, None)
                await self._broadcast_room(client.room_id, {
                    "type": "visitor_left",
                    "visitor_id": client.visitor_id,
                    "visitor_name": client.visitor_name
                })

    async def _handle_message(self, client: WSClient, msg: dict):
        """Route incoming WebSocket messages."""
        msg_type = msg.get("type", "")

        if msg_type == "chat":
            # Visitor sends a message — broadcast to room
            text = msg.get("text", "").strip()
            if not text:
                return

            # Broadcast the message to all visitors in the room
            await self._broadcast_room(client.room_id, {
                "type": "chat",
                "visitor_id": client.visitor_id,
                "visitor_name": client.visitor_name,
                "text": text,
                "time": time.time()
            }, exclude=client.session_id)

            # Also send to the sender as confirmation
            await self._send(client, {
                "type": "chat_sent",
                "text": text,
                "time": time.time()
            })

        elif msg_type == "move":
            # Visitor moves to a new room
            target = msg.get("room_id")
            direction = msg.get("direction")
            old_room = client.room_id

            if target:
                new_room = target
            elif direction:
                new_room = self.ide.room_manager.get_exit_target(client.room_id, direction)
                if not new_room:
                    await self._send(client, {"type": "error", "error": f"Can't go {direction}"})
                    return
            else:
                return

            client.room_id = new_room
            if client.session_id in self.ide.sessions:
                self.ide.sessions[client.session_id]["room"] = new_room

            # Broadcast departure from old room
            await self._broadcast_room(old_room, {
                "type": "visitor_left",
                "visitor_id": client.visitor_id,
                "visitor_name": client.visitor_name,
                "direction": direction
            }, exclude=client.session_id)

            # Send new room info to mover
            room = self.ide.room_manager.get(new_room)
            visitors = [c.to_dict() for c in self.clients.values() if c.room_id == new_room]
            await self._send(client, {
                "type": "room_changed",
                "room_id": new_room,
                "room_name": room.name if room else "Unknown",
                "description": room.description if room else "",
                "npc": {
                    "name": room.npc.name,
                    "greeting": room.npc.greeting,
                    "personality": room.npc.personality if room.npc else ""
                } if room and room.npc else None,
                "exits": [{"direction": e.direction, "target": e.target_room} for e in room.exits] if room else [],
                "visitors": visitors
            })

            # Broadcast arrival to new room
            await self._broadcast_room(new_room, {
                "type": "visitor_arrived",
                "visitor": client.to_dict()
            }, exclude=client.session_id)

        elif msg_type == "ask":
            # Ask NPC — result broadcasts to room
            question = msg.get("question", "").strip()
            if not question:
                return

            room = self.ide.room_manager.get(client.room_id)
            personality = room.npc.personality if room and room.npc else ""
            result = self.ide.npc.handle_query(
                client.room_id, client.visitor_id, question, personality
            )

            npc_response = {
                "type": "npc_response",
                "room_id": client.room_id,
                "npc_name": room.npc.name if room and room.npc else "NPC",
                "question": question,
                "response": result["response"],
                "tier": result["tier"],
                "confidence": result["confidence"],
                "new_tile": result["new_tile_created"],
                "asker": client.visitor_name,
                "time": time.time()
            }

            # Everyone in the room sees NPC responses (like overhearing at a bar)
            await self._broadcast_room(client.room_id, npc_response)

        elif msg_type == "tile_added":
            # Broadcast new tile to room
            await self._broadcast_room(client.room_id, {
                "type": "tile_added",
                "tile_id": msg.get("tile_id"),
                "question": msg.get("question", "")[:60],
                "added_by": client.visitor_name,
                "time": time.time()
            })

        elif msg_type == "heartbeat":
            client.last_heartbeat = time.time()

    async def _send(self, client: WSClient, data: dict):
        """Send a message to a specific client."""
        try:
            await client.ws.send(json.dumps(data))
        except:
            self.clients.pop(client.session_id, None)

    async def _broadcast_room(self, room_id: str, data: dict, exclude: str = None):
        """Broadcast a message to all clients in a room."""
        for sid, client in list(self.clients.items()):
            if client.room_id == room_id and sid != exclude:
                await self._send(client, data)

    async def broadcast(self, room_id: str, data: dict):
        """Public API: broadcast to a room (for scripts, agents, etc.)."""
        await self._broadcast_room(room_id, data)

    def get_room_visitors(self, room_id: str) -> list:
        """Get all visitors currently in a room."""
        return [c.to_dict() for c in self.clients.values() if c.room_id == room_id]

    def get_all_visitors(self) -> list:
        """Get all connected visitors."""
        return [c.to_dict() for c in self.clients.values()]
