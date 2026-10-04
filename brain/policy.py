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
Hint ladder: the first nudge names what the student was doing and the line
("Check how you took the derivative on line 1."). If they ask again, keep
writing with the mistake still there, or go quiet for STUCK_AFTER_S, the
otter gives Gemini's more specific `hint` once ("Look at what happened to the
x when you took the derivative on line 1."). Never the fix.
When the student SAID something (mic, tap `t`), Gemini's `reply` is spoken
instead, if it passes its own filter (no symbols, worked answers or rule names).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .prompts import FORBIDDEN_IN_NUDGE
from .schemas import BoardAnalysis, Mood, Step, StepStatus
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
    StepStatus.WRONG_RULE: "Hmm, take another look at which rule you picked when you {act} on line {n}.",
    StepStatus.MISAPPLIED: "Check how you {act} on line {n}.",
    StepStatus.ARITHMETIC: "Double-check the arithmetic when you {act} on line {n}.",
}
# What the student was doing, when Gemini's own phrase for it can't be used.
TOPIC_ACTION = {"derivative": "took the derivative", "integral": "integrated", "algebra": "simplified",
                "trig": "rewrote the trig expression", "other": "worked it out"}
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


def _problem_key(a: BoardAnalysis) -> str:
    return a.problem.strip() or a.board_text.strip()[:80]


def _flag_key(a: BoardAnalysis, fe: Step) -> tuple[str, int, str, str]:
    """Includes what's written on the line: rewriting '= 2' as '= 8' is a new
    attempt and deserves a new nudge; re-reading the same '= 2' does not."""
    return (_problem_key(a), fe.line, fe.status.value, _norm(fe.latex))


RULE_NAMES = FORBIDDEN_IN_NUDGE[:FORBIDDEN_IN_NUDGE.index("squeeze") + 1]
CHAT_FALLBACK = "Good question! Try the next step on the board and I'll check it with you."
# A reply to the student may talk about anything, but never in symbols or with a
# worked answer: 'x^2', '8x', '=', LaTeX, 'the answer is', or a rule's name.
_MATHY = re.compile(r"\\[a-z]+|\^|=|\b\d+[a-z]\b|the answer is|equals")


_ORDINAL = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth"}
_WORD = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def mentions_line(text: str, n: int) -> bool:
    """'line 2', 'line two', 'the second line', 'your 2nd line'."""
    names = [str(n)] + ([_WORD[n]] if n in _WORD else [])
    pre = [rf"{n}(st|nd|rd|th)"] + ([_ORDINAL[n]] if n in _ORDINAL else [])
    pat = rf"\bline ({'|'.join(names)})\b|\b({'|'.join(pre)}) line\b"
    return re.search(pat, text.lower()) is not None


def reply_is_safe(text: str) -> bool:
    low = text.lower()
    return not (_MATHY.search(low) or any(r in low for r in RULE_NAMES))


def gives_too_much(text: str) -> bool:
    """A rule's name, corrected math, symbols: anything that hands over the fix."""
    low = text.lower()
    return any(w in low for w in FORBIDDEN_IN_NUDGE) or bool(re.search(r"\\[a-z]+|\^|\d\s*[a-z]\b", low))


def action_for(a: BoardAnalysis, fe: Step) -> str:
    """'took the derivative': Gemini's phrase for the line if it's safe and short, else the topic's."""
    act = (fe.action or "").strip().rstrip(".")
    if act and len(act.split()) <= 6 and not gives_too_much(act):
        return act
    return TOPIC_ACTION.get(a.topic, TOPIC_ACTION["other"])


def hint_for(a: BoardAnalysis, fe: Step) -> str:
    """The second, more specific hint, or "" if Gemini's would give too much away."""
    h = a.hint.strip()
    return h if h and not gives_too_much(h) else ""


def sanitize_nudge(text: str, kind: StepStatus | None, line: int | None, act: str = "worked it out") -> str:
    """Enforce 'never give the fix' even if the model slipped."""
    if gives_too_much(text) or not text.strip():
        tmpl = SAFE_NUDGE.get(kind or StepStatus.WRONG_RULE, SAFE_NUDGE[StepStatus.WRONG_RULE])
        return tmpl.format(n=line if line is not None else "that", act=act)
    return text.strip()


@dataclass
class Policy:
    threshold: float = 0.7
    cooldown_s: float = 20.0
    _flagged: dict[tuple[str, int, str, str], int] = field(default_factory=dict)   # mistake -> hints said (1, 2)
    _pending: tuple[tuple[str, int, str, str], Decision] | None = None  # 2nd hint for the latest mistake
    _praised: set[str] = field(default_factory=set)
    _last_spoke: float = -1e9

    def decide(self, a: BoardAnalysis, v: VerifierResult | None = None, now: float | None = None,
               on_demand: bool = False, said: str | None = None) -> Decision:
        """Auto checks stay quiet unless there's something new to say. When the
        student asks (on_demand: the `c` key, app button, "check my work"), the
        otter always answers, still without ever giving away the fix. When they
        said something (`said`, from the mic), it answers what they said."""
        now = time.monotonic() if now is None else now
        fe = a.first_error
        if self._pending and (fe is None or self._pending[0] != _flag_key(a, fe)):
            self._pending = None             # fixed, or a different mistake now: that hint is stale
        if said and (d := self._reply(a, v, now)) is not None:
            return d
        d = self._decide_auto(a, v, now)
        if (on_demand or said) and not d.speak:
            d = self._answer(a, v, d)
            self._last_spoke = now
        return d

    def _reply(self, a: BoardAnalysis, v: VerifierResult | None, now: float) -> Decision | None:
        """Gemini's answer to what the student said, if it's safe to say.
        None = fall back to the board-based answer."""
        text = a.reply.strip()
        if not text:
            return None
        fe = a.first_error
        about = fe is not None and (a.reply_about_error or mentions_line(text, fe.line))
        if about and v is not None and v.veto_line == fe.line:
            return None                      # it's about a "mistake" SymPy says isn't one
        if not reply_is_safe(text):
            if about:
                return None                  # say the vetted nudge instead
            text = CHAT_FALLBACK
        self._last_spoke = now
        if about and a.board_complete and a.confidence >= self.threshold:
            # it's pointing out the flagged line: aim the laser, and don't repeat it on the next auto check
            self._flag(a, fe)
            return Decision(True, text, mood="confused", line=fe.line, kind=fe.status, box=fe.box, reason="reply")
        return Decision(True, text, mood="happy", reason="reply")

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
            # asked about a mistake it already pointed out: one step more specific, and point again
            if self._flagged.get(_flag_key(a, fe), 0) >= 1 and (d := self._hint(a, fe, "asked")) is not None:
                return d
            self._flag(a, fe)
            return self._nudge(a, fe, "asked")
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
        key_problem = _problem_key(a)

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

        level = self._flagged.get(_flag_key(a, fe), 0)
        quiet = Decision(False, mood="confused", line=fe.line, kind=fe.status, box=fe.box, reason="already flagged")
        if level >= 2 or (level == 1 and not hint_for(a, fe)):
            return quiet
        if now - self._last_spoke < self.cooldown_s:
            return Decision(False, mood="confused", line=fe.line, kind=fe.status, box=fe.box, reason="cooldown")
        self._last_spoke = now
        if level == 1:                       # kept going with the mistake still there: more specific
            return self._hint(a, fe, "hint") or quiet
        self._flag(a, fe)
        return self._nudge(a, fe, "flag")

    # ---- the hint ladder ----------------------------------------------------
    def _nudge(self, a: BoardAnalysis, fe: Step, reason: str) -> Decision:
        return Decision(True, sanitize_nudge(a.nudge, fe.status, fe.line, action_for(a, fe)), mood="confused",
                        line=fe.line, kind=fe.status, box=fe.box, reason=reason)

    def _hint(self, a: BoardAnalysis, fe: Step, reason: str) -> Decision | None:
        hint = hint_for(a, fe)
        if not hint:
            return None
        self._flagged[_flag_key(a, fe)] = 2
        self._pending = None
        return Decision(True, hint, mood="confused", line=fe.line, kind=fe.status, box=fe.box, reason=reason)

    def _flag(self, a: BoardAnalysis, fe: Step) -> None:
        """The first nudge for this mistake was said; keep its 2nd hint for later."""
        key = _flag_key(a, fe)
        self._flagged[key] = max(1, self._flagged.get(key, 0))
        hint = hint_for(a, fe)
        self._pending = ((key, Decision(True, hint, mood="confused", line=fe.line, kind=fe.status, box=fe.box,
                                        reason="stuck hint"))
                         if hint and self._flagged[key] == 1 else None)

    def escalate(self, now: float | None = None) -> Decision | None:
        """The student went quiet with a pointed-out mistake still on the board:
        its more specific hint, once. None when there's nothing pending."""
        if self._pending is None:
            return None
        key, d = self._pending
        self._pending = None
        self._flagged[key] = 2
        self._last_spoke = time.monotonic() if now is None else now
        return d

    def reset(self) -> None:
        self._flagged.clear()
        self._pending = None
        self._praised.clear()
        self._last_spoke = -1e9
