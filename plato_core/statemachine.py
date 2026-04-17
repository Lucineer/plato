"""
PLATO State Machine — Mermaid stateDiagram-v2 as executable routing logic.

Room authors define agent flow with Mermaid diagrams. The runtime parses
the diagram, builds a transition table, and routes agent behavior.

Lightweight: pure Python, no external deps, regex-based parsing.
"""

import re
from typing import Dict, Optional, Tuple


class StateMachine:
    """Executable state machine from Mermaid stateDiagram-v2."""

    def __init__(self, mermaid_text: str = ""):
        self.initial: Optional[str] = None
        self.final: Optional[str] = None
        self.states: set = set()
        self.transitions: Dict[str, Dict[str, str]] = {}
        self.current: Optional[str] = None
        self.history: list = []

        if mermaid_text:
            self.load(mermaid_text)

    def load(self, mermaid_text: str):
        """Parse Mermaid stateDiagram-v2 into a transition table."""
        self.transitions = {}
        self.states = set()
        self.initial = None
        self.final = None

        for line in mermaid_text.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('%%') or line.startswith('stateDiagram'):
                continue
            self._parse_line(line)

        if self.initial:
            self.current = self.initial

    def _parse_line(self, line: str):
        line = line.split('%%')[0].strip()

        # Pattern: State1 --> State2 : label
        # Pattern: [*] --> State1 (initial)
        # Pattern: StateN --> [*] (final)
        pattern = r'^\s*(\S+)\s*-->\s*(\S+)(?:\s*:\s*(.+))?$'
        match = re.match(pattern, line)
        if not match:
            return

        frm = match.group(1).strip()
        to = match.group(2).strip()
        label = match.group(3).strip() if match.group(3) else None

        if frm == '[*]':
            self.initial = to
            self.states.add(to)
            return
        if to == '[*]':
            self.final = frm
            self.states.add(frm)
            return

        self.states.add(frm)
        self.states.add(to)

        if frm not in self.transitions:
            self.transitions[frm] = {}

        key = self._normalize(label) if label else '_default'
        self.transitions[frm][key] = to

    @staticmethod
    def _normalize(label: str) -> str:
        return re.sub(r'[^a-z0-9]', '_', label.strip().lower())

    def transition(self, trigger: str) -> Optional[str]:
        """Attempt a state transition based on a trigger string.

        Checks if any transition label appears in the trigger.
        Returns the new state name, or None if no transition matched.
        """
        if not self.current or self.current not in self.transitions:
            return None

        trigger_lower = trigger.lower()
        trans = self.transitions[self.current]

        # Check all transitions from current state
        for label, target in trans.items():
            if label == '_default':
                continue
            # Check if the normalized label words appear in trigger
            words = label.replace('_', ' ')
            if words in trigger_lower:
                self.history.append((self.current, target, trigger))
                self.current = target
                return target

        # Check default transition (no label)
        if '_default' in trans:
            target = trans['_default']
            self.history.append((self.current, target, trigger))
            self.current = target
            return target

        # If only one non-default transition exists, fire it (unambiguous)
        non_default = {k: v for k, v in trans.items() if k != '_default'}
        if len(non_default) == 1:
            label, target = next(iter(non_default.items()))
            self.history.append((self.current, target, trigger))
            self.current = target
            return target

        return None

    def can_transition(self, trigger: str) -> Tuple[bool, Optional[str]]:
        """Check if a transition would fire without actually firing it."""
        if not self.current or self.current not in self.transitions:
            return False, None

        trigger_lower = trigger.lower()
        trans = self.transitions[self.current]

        for label, target in trans.items():
            if label == '_default':
                continue
            words = label.replace('_', ' ')
            if words in trigger_lower:
                return True, target

        if '_default' in trans:
            return True, trans['_default']

        # Unambiguous single path
        non_default = {k: v for k, v in trans.items() if k != '_default'}
        if len(non_default) == 1:
            return True, next(iter(non_default.values()))

        return False, None

    def reset(self):
        self.current = self.initial
        self.history = []

    def to_dict(self) -> dict:
        return {
            'current': self.current,
            'initial': self.initial,
            'final': self.final,
            'states': sorted(self.states),
            'transitions': self.transitions,
            'history_length': len(self.history)
        }

    def __repr__(self):
        return f"StateMachine(current={self.current}, states={len(self.states)}, transitions={sum(len(v) for v in self.transitions.values())})"
