"""Session memory: what we've checked, said, and heard. Feeds prompt context
and the end-of-session summary. Sinks (Tiger Data, Snowflake, ...) subscribe
to `on_check` and get one row per check.
"""

from __future__ import annotations

import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from .policy import Decision
from .schemas import BoardAnalysis, SessionSummary, StepStatus
from .verifier import VerifierResult

CheckSink = Callable[["CheckRecord"], None]


@dataclass
class CheckRecord:
    ts: float
    session_id: str
    analysis: BoardAnalysis
    verifier: VerifierResult
    decision: Decision
    on_demand: bool

    def row(self) -> dict[str, Any]:
        """Flat dict for a database insert."""
        fe = self.analysis.first_error
        return {
            "session_id": self.session_id,
            "ts": self.ts,
            "topic": self.analysis.topic,
            "problem": self.analysis.problem,
            "confidence": self.analysis.confidence,
            "board_complete": self.analysis.board_complete,
            "error_line": fe.line if fe else None,
            "error_kind": fe.status.value if fe else None,
            "rule_used": fe.rule_used if fe else None,
            "rule_expected": fe.rule_expected if fe else None,
            "sympy_veto": self.verifier.veto_line is not None,
            "spoke": self.decision.speak,
            "nudge": self.decision.text if self.decision.speak else None,
            "on_demand": self.on_demand,
        }


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    started: float = field(default_factory=time.time)
    checks: list[CheckRecord] = field(default_factory=list)
    nudges: list[str] = field(default_factory=list)
    heard: list[str] = field(default_factory=list)       # push-to-talk transcripts
    sinks: list[CheckSink] = field(default_factory=list)

    # ---- recording -----------------------------------------------------
    def add_check(self, a: BoardAnalysis, v: VerifierResult, d: Decision, on_demand: bool = False) -> CheckRecord:
        rec = CheckRecord(time.time(), self.id, a, v, d, on_demand)
        self.checks.append(rec)
        if d.speak and d.kind is not None:
            self.nudges.append(d.text)
        for sink in self.sinks:
            try:
                sink(rec)
            except Exception:  # a dead database must never stop the tutor
                pass
        return rec

    def add_heard(self, text: str) -> None:
        if text.strip():
            self.heard.append(text.strip())

    # ---- for the next prompt -------------------------------------------
    def context(self, on_demand: bool = False) -> dict[str, Any]:
        last = self.checks[-1].analysis if self.checks else None
        return {
            "previous_nudges": self.nudges[-3:],
            "student_said": self.heard[-1] if self.heard else None,
            "last_problem": last.problem if last and last.problem else None,
            "on_demand": on_demand,
        }

    def consume_heard(self) -> None:
        """Student's words are used for exactly one check, then cleared."""
        self.heard.clear()

    # ---- wrap-up -------------------------------------------------------
    def summary(self) -> SessionSummary:
        kinds = Counter(
            c.analysis.first_error.status.value
            for c in self.checks
            if c.decision.speak and c.analysis.first_error is not None
        )
        review = None
        for c in self.checks:
            fe = c.analysis.first_error
            if c.decision.speak and fe is not None and fe.status == StepStatus.WRONG_RULE:
                review = f"Line {fe.line} of {c.analysis.problem or 'the problem'}: {fe.note or 'rule choice'}"
                break
        if review is None and kinds:
            top = kinds.most_common(1)[0][0]
            review = f"Most frequent slip: {top.replace('_', ' ')}"
        return SessionSummary(
            checks=len(self.checks),
            mistakes_by_kind=dict(kinds),
            one_to_review=review,
            duration_s=round(time.time() - self.started, 1),
        )
