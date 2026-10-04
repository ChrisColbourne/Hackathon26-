"""Canned Gemini answers, for building everything else without burning quota.

  python -m brain.run_cli --camera --show --mock
  GEMINI_MOCK=1 python -m brain.server

Same interface as GeminiBrain.see(). The image is ignored; each call "thinks"
for ~1.5 s and returns the next verdict in the cycle (wrong rule, all correct,
arithmetic slip). The problem changes slightly every round so the policy's
flag-once rule doesn't silence the otter after the first lap. MOCK_CASE pins
one case.
"""

from __future__ import annotations

import logging
import time

from . import config
from .schemas import BoardAnalysis, Step

log = logging.getLogger("mock")


def _derivative_cases(n: int) -> dict[str, BoardAnalysis]:
    problem = rf"\frac{{d}}{{dx}}[x^{n} \sin x]"
    l1 = Step(line=1, latex=problem, status="ok", box=[120, 80, 220, 700])
    wrong = Step(line=2, latex=rf"\frac{{{n}x^{n - 1} \sin x - x^{n} \cos x}}{{\sin^2 x}}", status="wrong_rule",
                 rule_used="quotient_rule", rule_expected="product_rule", box=[260, 80, 380, 900],
                 note="Quotient rule applied to a product.")
    right = Step(line=2, latex=rf"{n}x^{n - 1} \sin x + x^{n} \cos x", status="ok", box=[260, 80, 380, 900])
    return {
        "wrong_rule": BoardAnalysis(
            board_text=f"d/dx [x^{n} sin x] = ({n}x^{n - 1} sin x - x^{n} cos x) / sin^2 x", problem=problem,
            topic="derivative", board_complete=True, steps=[l1, wrong], first_error_line=2, confidence=0.93,
            nudge="Hmm, take another look at which rule fits line 2.", mood="confused"),
        "correct": BoardAnalysis(
            board_text=f"d/dx [x^{n} sin x] = {n}x^{n - 1} sin x + x^{n} cos x", problem=problem,
            topic="derivative", board_complete=True, steps=[l1, right], first_error_line=None, confidence=0.97,
            nudge="", mood="happy"),
    }


def _algebra_case(n: int) -> BoardAnalysis:
    rhs = 7 + n
    return BoardAnalysis(
        board_text=f"2x + 3 = {rhs}\n2x = {rhs + 3}\nx = {(rhs + 3) / 2:g}", problem=f"2x + 3 = {rhs}",
        topic="algebra", board_complete=True,
        steps=[Step(line=1, latex=f"2x + 3 = {rhs}", status="ok", box=[100, 80, 200, 600]),
               Step(line=2, latex=f"2x = {rhs + 3}", status="arithmetic", box=[240, 80, 340, 600],
                    note="Added 3 instead of subtracting when moving it across."),
               Step(line=3, latex=f"x = {(rhs + 3) / 2:g}", status="ok", box=[380, 80, 480, 600])],
        first_error_line=2, confidence=0.9, nudge="Something in the arithmetic on line 2 doesn't add up.",
        mood="confused")


ORDER = ("wrong_rule", "correct", "arithmetic")


class MockBrain:
    chain = [("mock", "-")]

    def __init__(self, case: str = config.MOCK_CASE, delay_s: float = 1.5, **_: object):
        if case != "cycle" and case not in ORDER:
            raise ValueError(f"MOCK_CASE must be cycle or one of {ORDER}")
        self.case, self.delay_s = case, delay_s
        self.calls = 0
        self.last_model = "mock"
        self.last_raw: str | None = None

    def see(self, jpeg: bytes, context: dict | None = None) -> BoardAnalysis:
        time.sleep(self.delay_s)
        name = self.case if self.case != "cycle" else ORDER[self.calls % len(ORDER)]
        round_no = self.calls // len(ORDER)
        n = 2 + round_no
        a = _algebra_case(round_no) if name == "arithmetic" else _derivative_cases(n)[name]
        self.calls += 1
        self.last_raw = a.model_dump_json()
        log.info("mock verdict #%d: %s (conf %.2f)", self.calls, name, a.confidence)
        return a
