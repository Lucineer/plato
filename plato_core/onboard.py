"""
PLATO Onboarding — Determine visitor type and place them in the right room.

Asks questions, detects intent, and spawns the visitor in the appropriate
starting room for their use case.
"""

import json, os
from typing import Optional, Tuple
from plato_core.rooms import RoomManager


PERSONAS = {
    "novelist": {
        "keywords": ["write", "novel", "story", "character", "world-build", "fiction",
                      "book", "narrative", "plot", "scene", "chapter", "creative writing"],
        "description": "A world-building novelist starting in their creative house",
        "starting_room": "novelist_study",
        "greeting": "Welcome to your writing room. Your characters and worlds are organized here. What story are you working on?"
    },
    "teacher": {
        "keywords": ["teach", "student", "class", "lesson", "course", "curriculum",
                      "school", "education", "learn", "classroom", "homework"],
        "description": "A teacher managing a classroom and curriculum",
        "starting_room": "classroom_main",
        "greeting": "Welcome to your classroom. Your lessons and student interactions are organized by subject. What are you teaching?"
    },
    "student": {
        "keywords": ["study", "learn", "homework", "exam", "course", "lecture",
                      "university", "college", "textbook", "tutor"],
        "description": "A student stepping into a learning environment",
        "starting_room": "classroom_study",
        "greeting": "Welcome to the study room. Ask questions about any subject — the accumulated wisdom of every student who came before is here."
    },
    "business": {
        "keywords": ["business", "startup", "company", "project", "plan", "strategy",
                      "product", "market", "customer", "revenue", "digital twin", "sandbox"],
        "description": "A business professional creating a digital twin of their project",
        "starting_room": "business_hub",
        "greeting": "Welcome to your project sandbox. Map your ideas, track decisions, and build your business's operational memory. What are you building?"
    },
    "game_dev": {
        "keywords": ["game", "level", "mechanic", "player", "enemy", "boss",
                      "rpg", "npc", "quest", "item", "inventory", "map", "unity", "unreal"],
        "description": "A game developer designing levels and logic",
        "starting_room": "game_workshop",
        "greeting": "Welcome to the game workshop. Your levels, mechanics, and design decisions live here. What game are you building?"
    },
    "harbor": {
        "keywords": ["dock", "boat", "ship", "harbor", "marina", "vessel",
                      "port", "berth", "mooring", "ocr", "camera", "fleet", "log"],
        "description": "A harbor master managing docks with camera/OCR integration",
        "starting_room": "harbor_dock",
        "greeting": "Welcome to the harbor. Your docks, vessels, and movement logs are tracked here. Camera snapshots and OCR readings are logged in real-time."
    },
    "developer": {
        "keywords": ["code", "program", "software", "api", "debug", "deploy",
                      "git", "repo", "bug", "feature", "library", "framework"],
        "description": "A software developer maintaining a project",
        "starting_room": "dev_workshop",
        "greeting": "Welcome to the dev workshop. Your codebase decisions, debugging sessions, and deployment history are organized here. What are you working on?"
    },
    "explorer": {
        "keywords": [],
        "description": "A curious visitor exploring PLATO for the first time",
        "starting_room": "plato_entrance",
        "greeting": "Welcome to PLATO. This is a space where experience accumulates. Walk around, ask questions, and leave tiles for future visitors."
    }
}


def detect_persona(text: str) -> str:
    """Detect visitor type from their description."""
    text_lower = text.lower()
    scores = {}
    for persona, info in PERSONAS.items():
        if persona == "explorer":
            continue
        score = sum(1 for kw in info["keywords"] if kw in text_lower)
        scores[persona] = score
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "explorer"


def get_persona_info(persona: str) -> dict:
    """Get persona metadata."""
    return PERSONAS.get(persona, PERSONAS["explorer"])


def onboard_questions() -> list:
    """Return the onboarding question sequence."""
    return [
        {
            "id": "name",
            "question": "What should we call you?",
            "placeholder": "Your name or handle",
            "required": True
        },
        {
            "id": "purpose",
            "question": "What brings you to PLATO? Describe what you're working on in a sentence or two.",
            "placeholder": "e.g., I'm writing a fantasy novel about parallel universes...",
            "required": True,
            "detect_persona": True
        },
        {
            "id": "experience",
            "question": "Have you used PLATO or similar systems before?",
            "options": ["First time", "I've visited a PLATO before", "I run my own PLATO"],
            "required": False
        },
        {
            "id": "model_endpoint",
            "question": "Do you have an LLM API endpoint for the NPC layer? (leave blank for tile-only mode)",
            "placeholder": "https://api.deepseek.com/v1/chat/completions",
            "required": False
        }
    ]


def process_onboarding(answers: dict, room_manager: RoomManager) -> dict:
    """Process onboarding answers and return visitor profile."""
    name = answers.get("name", "visitor")
    purpose = answers.get("purpose", "")
    persona = detect_persona(purpose)
    persona_info = get_persona_info(persona)

    # Try to find the starting room
    starting_room = None
    if room_manager:
        # Look for exact match first
        room = room_manager.get(persona_info["starting_room"])
        if room:
            starting_room = persona_info["starting_room"]
        else:
            # Fall back to theme
            themed = room_manager.get_by_theme(persona)
            if themed:
                starting_room = themed[0].room_id

    if not starting_room:
        starting_room = "plato_entrance"

    return {
        "visitor_id": name.lower().replace(" ", "_"),
        "visitor_name": name,
        "persona": persona,
        "persona_description": persona_info["description"],
        "starting_room": starting_room,
        "greeting": persona_info["greeting"],
        "purpose": purpose,
        "experience": answers.get("experience", "First time"),
        "model_endpoint": answers.get("model_endpoint", ""),
        "permissions": "write"  # New visitors get write access
    }
