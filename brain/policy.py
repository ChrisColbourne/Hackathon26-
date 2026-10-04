"""Decide whether the otter speaks, and what it's allowed to say.

Inputs: Gemini's BoardAnalysis + the SymPy VerifierResult.
Rules, in order:
  1. Board incomplete            -> stay quiet (mood: thinking)
  2. Nothing wrong, work looks done, not yet praised -> "Nice work" once per problem
  3. Confidence below threshold  -> quiet
  4. SymPy vetoes the flagged line -> quiet
  5. Same (problem, line, kind) already flagged -> quiet
  6. Cooldown since last speech  -> quiet
  7. Nudge fails the word filter -> swap in a safe template
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .prompts import FORBIDDEN_IN_NUDGE
from .schemas import BoardAnalysis, Mood, StepStatus
from .verifier import VerifierResult

_NOISE = re.compile(r"\s+|\\left|\\right|\\[,;!]|\\displaystyle|[{}]")


def _norm(latex: str) -> str:
    """Normalise LaTeX enough to tell 'the problem, restated' from real work."""
    s = _NOISE.sub("", latex)
    return s.replace(r"\fracddx", "d/dx").replace(r"\dfracddx", "d/dx").rstrip("=.")


def has_work(a: BoardAnalysis) -> bool:
    """Is there anything on the board beyond the problem statement?

    Gemini groups by physical line, so 'd/dx(4x^2) = 8x' arrives as ONE step
    holding both the problem and the answer. Counting steps isn't enough.
    """
    if len(a.steps) >= 2:
        return True
    if not a.steps:
        return False
    step, prob = _norm(a.steps[0].latex), _norm(a.problem)
    if not step or step == prob:
        return False                                      # the problem, merely restated
    if "=" in prob:                                       # an equation to solve: any other line is work
        return True
    return "=" in step and bool(step.split("=")[-1])      # 'find d/dx ...': work means '= something'


SAFE_NUDGE = {
    StepStatus.WRONG_RULE: "Hmm, take another look at which rule fits line {n}.",
    StepStatus.MISAPPLIED: "Check how you applied that rule on line {n}.",
    StepStatus.ARITHMETIC: "Something in the arithmetic on line {n} doesn't add up.",
}
PRAISE = "Nice work, that all checks out."


@dataclass
class Decision:
    speak: bool
    text: str = ""
    mood: Mood = "idle"
    line: int | None = None
    kind: StepStatus | None = None
    box: list[int] | None = None
    reason: str = ""


def sanitize_nudge(text: str, kind: StepStatus | None, line: int | None) -> str:
    """Enforce 'never give the fix' even if the model slipped."""
    low = text.lower()
    bad = any(w in low for w in FORBIDDEN_IN_NUDGE) or bool(re.search(r"\\[a-z]+|\^|\d\s*[a-z]\b", low))
    if bad or not text.strip():
        tmpl = SAFE_NUDGE.get(kind or StepStatus.WRONG_RULE, SAFE_NUDGE[StepStatus.WRONG_RULE])
        return tmpl.format(n=line if line is not None else "that")
    return text.strip()


@dataclass
class Policy:
    threshold: float = 0.7
    cooldown_s: float = 20.0
    _flagged: set[tuple[str, int, str, str]] = field(default_factory=set)
    _praised: set[str] = field(default_factory=set)
    _last_spoke: float = -1e9

    def decide(self, a: BoardAnalysis, v: VerifierResult | None = None, now: float | None = None,
               on_demand: bool = False) -> Decision:
        """Auto checks stay quiet unless there's something new to say. When the
        student asks (on_demand: the `c` key, app button, "check my work"), the
        otter always answers, still without ever giving away the fix."""
        now = time.monotonic() if now is None else now
        d = self._decide_auto(a, v, now)
        if on_demand and not d.speak:
            d = self._answer(a, v, d)
            self._last_spoke = now
        return d

    def _answer(self, a: BoardAnalysis, v: VerifierResult | None, quiet: Decision) -> Decision:
        """What to say when asked, for each reason the auto check stayed quiet."""
        fe = a.first_error
        why = quiet.reason
        if why == "board incomplete":
            return Decision(True, "Finish writing that line, then ask me again.", mood="thinking", reason="asked")
        if fe is not None:
            if v is not None and v.veto_line == fe.line:
                return Decision(True, "That step looks right to me.", mood="happy", reason="asked")
            if why.startswith("confidence"):
                return Decision(True, "I can't read that clearly. Could you write it a little bigger?",
                                mood="thinking", reason="asked")
            # already flagged / cooldown: say it again, and point at it again
            return Decision(True, sanitize_nudge(a.nudge, fe.status, fe.line), mood="confused",
                            line=fe.line, kind=fe.status, box=fe.box, reason="asked")
        all_ok = bool(a.steps) and all(s.status == StepStatus.OK for s in a.steps)
        if all_ok and has_work(a):
            return Decision(True, "Yes, that all checks out.", mood="happy", reason="asked")
        if not has_work(a) and a.problem.strip():
            return Decision(True, "Go ahead and start. I'll check each step as you go.", mood="listening",
                            reason="asked")
        if not a.problem.strip():
            return Decision(True, "I don't see a problem on the board yet.", mood="thinking", reason="asked")
        return Decision(True, "I can't read part of that. Could you rewrite it more clearly?",
                        mood="thinking", reason="asked")

    def _decide_auto(self, a: BoardAnalysis, v: VerifierResult | None, now: float) -> Decision:
        key_problem = a.problem.strip() or a.board_text.strip()[:80]

        if not a.board_complete:
            return Decision(False, mood="thinking", reason="board incomplete")

        fe = a.first_error
        if fe is None:
            all_ok = bool(a.steps) and all(s.status == StepStatus.OK for s in a.steps)
            worked = has_work(a)
            if all_ok and worked and a.confidence >= self.threshold and key_problem not in self._praised:
                if now - self._last_spoke < self.cooldown_s:
                    return Decision(False, mood="happy", reason="cooldown")
                self._praised.add(key_problem)
                self._last_spoke = now
                return Decision(True, PRAISE, mood="happy", reason="all steps ok")
            if not worked and a.problem.strip():
                # Only the problem is on the board: the student is thinking. Look
                # attentive, say nothing. (Praise needs actual work.)
                return Decision(False, mood="listening", reason="problem written, no work yet")
            return Decision(False, mood="idle" if all_ok else "thinking", reason="nothing to flag")

        if a.confidence < self.threshold:
            return Decision(False, mood="thinking", line=fe.line, kind=fe.status,
                            reason=f"confidence {a.confidence:.2f} < {self.threshold}")
        if v is not None and v.veto_line == fe.line:
            return Decision(False, mood="idle", line=fe.line, kind=fe.status, reason=v.note)

        # Include what's written on the line: rewriting '= 2' as '= 8' is a new
        # attempt and deserves a new nudge; re-reading the same '= 2' does not.
        key = (key_problem, fe.line, fe.status.value, _norm(fe.latex))
        if key in self._flagged:
            return Decision(False, mood="confused", line=fe.line, kind=fe.status, box=fe.box,
                            reason="already flagged")
        if now - self._last_spoke < self.cooldown_s:
            return Decision(False, mood="confused", line=fe.line, kind=fe.status, box=fe.box, reason="cooldown")

        self._flagged.add(key)
        self._last_spoke = now
        return Decision(True, sanitize_nudge(a.nudge, fe.status, fe.line), mood="confused",
                        line=fe.line, kind=fe.status, box=fe.box, reason="flag")

    def reset(self) -> None:
        self._flagged.clear()
        self._praised.clear()
        self._last_spoke = -1e9
