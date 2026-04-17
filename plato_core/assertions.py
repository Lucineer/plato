"""
PLATO Assertion System — Markdown bullet points as executable guardrails.

Assertive Markdown: bullet points are assertions that agent responses must satisfy.
A secondary auditor checks every response. Violations trigger retry loops.

Assertion syntax:
    - [MUST] Patient age must be confirmed before diagnosis
    - [MUST NOT] Never recommend medication without dosage
    - [SHOULD] Offer 3 alternatives before suggesting a course
    - [WHEN confidence < 0.5] Trigger fallback response

Levels: global → room → tile (higher overrides lower)
"""

import re
import time
from typing import Dict, List, Optional, Tuple
from enum import Enum


class Severity(Enum):
    MUST = 'must'           # Hard constraint — violation blocks response
    MUST_NOT = 'must_not'   # Hard constraint — violation blocks response
    SHOULD = 'should'       # Soft constraint — violation warns but allows
    WHEN = 'when'           # Conditional — triggers when condition met


class Assertion:
    """A single assertive constraint."""

    def __init__(self, text: str, severity: Severity = Severity.SHOULD,
                 condition: str = "", source: str = ""):
        self.text = text
        self.severity = severity
        self.condition = condition  # for WHEN type
        self.source = source       # "room", "tile", "global"
        self.violations = 0        # count of times violated

    def check(self, response: str, context: dict = None) -> Tuple[bool, str]:
        """Check if a response satisfies this assertion.

        Returns (passed, reason). Reason explains why it failed.
        Uses keyword matching — not perfect but zero-dependency.
        """
        text_lower = self.text.lower()
        response_lower = response.lower()

        # Extract the actual constraint from the assertion text
        # "Never recommend medication without dosage"
        # → check that if "medication" appears, "dosage" also appears
        # "Patient age must be confirmed"
        # → check that "age" appears in response or context

        # MUST NOT: negative assertions
        if self.severity == Severity.MUST_NOT:
            # Check for compound: "Never X without Y" → if X then require Y
            compound = self._parse_compound(text_lower)
            if compound:
                trigger_words, required_words = compound
                trigger_found = any(w in response_lower for w in trigger_words)
                if trigger_found:
                    required_found = any(w in response_lower for w in required_words)
                    if not required_found:
                        return False, f"MUST NOT: {self.text}"
                return True, ""
            # Simple negative: extract forbidden patterns
            forbidden = self._extract_patterns(text_lower)
            for pattern in forbidden:
                if pattern in response_lower:
                    return False, f"MUST NOT: {self.text}"

        # MUST / SHOULD: positive assertions
        elif self.severity in (Severity.MUST, Severity.SHOULD):
            # Check if the requirement keywords appear
            required = self._extract_patterns(text_lower)
            if required:
                found = sum(1 for p in required if p in response_lower)
                if found == 0 and len(required) > 0:
                    return False, f"{self.severity.value.upper()}: {self.text} (none of: {required})"

        # WHEN: conditional
        elif self.severity == Severity.WHEN:
            if context:
                # Simple condition evaluation
                cond_key, cond_val = self._parse_condition(self.condition)
                if cond_key and cond_val:
                    actual = context.get(cond_key)
                    if actual is not None:
                        try:
                            if self._eval_condition(float(actual), cond_val):
                                # Condition met — check the assertion text
                                required = self._extract_patterns(text_lower)
                                if required:
                                    found = sum(1 for p in required if p in response_lower)
                                    if found == 0:
                                        return False, f"WHEN {self.condition}: {self.text}"
                        except (ValueError, TypeError):
                            pass

        return True, ""

    def _extract_patterns(self, text: str) -> List[str]:
        """Extract meaningful keywords from assertion text.
        Removes assertion prefix words and normalizes."""
        stop = {'must', 'should', 'never', 'always', 'before', 'after',
                'ensure', 'verify', 'confirm', 'check', 'without', 'with',
                'every', 'include', 'that', 'this', 'the', 'for', 'and', 'or',
                'not', 'also', 'more', 'than', 'from', 'into', 'about', 'when',
                'present', 'cases', 'complex', 'information'}
        words = re.findall(r'\b[a-z]{3,}\b', text)
        return [w for w in words if w not in stop]

    def _parse_compound(self, text: str) -> Optional[Tuple[List[str], List[str]]]:
        """Parse 'never X without Y' compound assertions.
        Returns (trigger_words, required_words) or None."""
        match = re.match(r'never\s+(.+?)\s+without\s+(.+)', text)
        if match:
            trigger = self._extract_patterns(match.group(1))
            required = self._extract_patterns(match.group(2))
            if trigger and required:
                return trigger, required
        return None

    def _parse_condition(self, condition: str) -> Tuple[str, str]:
        """Parse 'confidence < 0.5' into ('confidence', '<0.5')."""
        match = re.match(r'(\w+)\s*([<>=!]+)\s*([\d.]+)', condition)
        if match:
            return match.group(1), match.group(2) + match.group(3)
        return "", ""

    def _eval_condition(self, actual: float, cond: str) -> bool:
        """Evaluate a simple condition like '<0.5'."""
        try:
            op = re.match(r'([<>=!]+)', cond).group(1)
            val = float(re.search(r'[\d.]+', cond).group())
            if op == '<': return actual < val
            if op == '>': return actual > val
            if op == '<=': return actual <= val
            if op == '>=': return actual >= val
            if op == '==': return actual == val
            if op == '!=': return actual != val
        except (AttributeError, ValueError):
            pass
        return False

    def to_dict(self) -> dict:
        return {
            'text': self.text,
            'severity': self.severity.value,
            'condition': self.condition,
            'source': self.source,
            'violations': self.violations
        }


class AssertionEngine:
    """Checks agent responses against assertive constraints."""

    def __init__(self, max_retries: int = 3):
        self.assertions: List[Assertion] = []
        self.max_retries = max_retries
        self.violation_log: list = []

    def load_from_markdown(self, markdown: str, source: str = "room"):
        """Parse assertions from Markdown bullet points.

        Syntax:
            - [MUST] assertion text
            - [MUST NOT] assertion text
            - [SHOULD] assertion text
            - [WHEN condition] assertion text
            - assertion text  (defaults to SHOULD)
        """
        for line in markdown.strip().split('\n'):
            line = line.strip()
            if not line.startswith('-'):
                continue

            # Remove the bullet
            text = line[1:].strip()

            # Parse severity tag
            severity = Severity.SHOULD
            condition = ""

            for sev in Severity:
                tag = f"[{sev.value.upper()}]"
                tag2 = f"[{sev.value.upper().replace('_', ' ')}]"
                if text.upper().startswith(tag):
                    text = text[len(tag):].strip()
                    severity = sev
                    break
                if text.upper().startswith(tag2):
                    text = text[len(tag2):].strip()
                    severity = sev
                    break

            # Extract condition for WHEN type
            if severity == Severity.WHEN:
                match = re.match(r'(.+?)\]\s*(.+)', text, re.IGNORECASE)
                if match:
                    condition = match.group(1).strip()
                    text = match.group(2).strip()

            if text:
                self.assertions.append(Assertion(text, severity, condition, source))

    def check(self, response: str, context: dict = None) -> Tuple[bool, List[dict]]:
        """Check a response against all assertions.

        Returns (all_passed, list_of_failures).
        Each failure: {'assertion': text, 'severity': str, 'reason': str}
        """
        failures = []
        for assertion in self.assertions:
            passed, reason = assertion.check(response, context)
            if not passed:
                assertion.violations += 1
                failures.append({
                    'assertion': assertion.text,
                    'severity': assertion.severity.value,
                    'reason': reason
                })
                self.violation_log.append({
                    'time': time.time(),
                    'assertion': assertion.text,
                    'reason': reason,
                    'response_preview': response[:100]
                })

        return len(failures) == 0, failures

    def should_block(self, failures: List[dict]) -> bool:
        """Determine if failures should block the response."""
        return any(f['severity'] in ('must', 'must_not') for f in failures)

    def should_warn(self, failures: List[dict]) -> bool:
        """Determine if failures should warn (but not block)."""
        return any(f['severity'] == 'should' for f in failures)

    @property
    def hard_assertions(self) -> int:
        return sum(1 for a in self.assertions if a.severity in (Severity.MUST, Severity.MUST_NOT))

    @property
    def soft_assertions(self) -> int:
        return sum(1 for a in self.assertions if a.severity == Severity.SHOULD)

    def to_dict(self) -> dict:
        return {
            'total': len(self.assertions),
            'hard': self.hard_assertions,
            'soft': self.soft_assertions,
            'violations_total': sum(a.violations for a in self.assertions),
            'assertions': [a.to_dict() for a in self.assertions]
        }
