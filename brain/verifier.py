"""SymPy double-check of Gemini's verdict.

Gemini reads the board; SymPy does the math. The biggest demo risk is the otter
flagging work that is actually correct, so the verifier's main power is the
VETO: if Gemini flags line N but SymPy finds line N mathematically equivalent
to a correct step, the policy stays quiet.

Everything here is best-effort. Handwritten LaTeX from a vision model often
won't parse; when it doesn't, we return None ("unknown") and defer to Gemini.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

import sympy as sp

from .schemas import BoardAnalysis, StepStatus

try:
    from latex2sympy2 import latex2sympy  # type: ignore

    AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    AVAILABLE = False

x = sp.Symbol("x")


@dataclass
class VerifierResult:
    available: bool
    # line -> True (equivalent to a correct step), False (not), None (couldn't tell)
    line_ok: dict[int, bool | None] = field(default_factory=dict)
    veto_line: int | None = None             # Gemini flagged it, SymPy says it's fine
    disagreements: list[str] = field(default_factory=list)  # Gemini ok, SymPy not
    note: str = ""


# ---- parsing helpers -----------------------------------------------------

_DDX = re.compile(r"\\frac\{d\}\{dx\}|\\dfrac\{d\}\{dx\}|d/dx|\\frac\{\\mathrm\{d\}\}\{\\mathrm\{d\}x\}")
_INT = re.compile(r"\\int\s*(.*?)\s*\\?,?\s*(?:\\mathrm\{d\}|d)x", re.S)


def _clean(s: str) -> str:
    s = s.replace(r"\left", "").replace(r"\right", "").replace(r"\,", "").replace(r"\;", "")
    s = s.replace(r"\cdot", "*").replace("[", "(").replace("]", ")")
    return s.strip().rstrip(".")


def _rhs(latex: str) -> str:
    """For 'a = b = c' take the last non-empty side; that's the student's result."""
    parts = [p.strip() for p in latex.split("=") if p.strip()]
    return parts[-1] if parts else latex


def _parse(latex: str) -> sp.Expr | None:
    if not AVAILABLE:
        return None
    try:
        expr = latex2sympy(_clean(latex))
        if isinstance(expr, (list, tuple)):
            return None
        return sp.sympify(expr).doit()  # evaluates any leftover Derivative/Integral
    except Exception:
        return None


def _equiv(a: sp.Expr, b: sp.Expr, trials: int = 6) -> bool | None:
    """Numeric equivalence at random points; symbolic simplify as a tie-break."""
    try:
        syms = sorted((a - b).free_symbols, key=lambda s: s.name)
        if not syms:
            return bool(sp.simplify(a - b) == 0)
        rng = random.Random(7)
        hits = 0
        for _ in range(trials):
            subs = {s: rng.uniform(0.3, 2.3) for s in syms}
            va, vb = complex(a.evalf(subs=subs)), complex(b.evalf(subs=subs))
            if any(abs(v) > 1e8 for v in (va, vb)):
                continue
            if abs(va - vb) > 1e-6 * max(1.0, abs(va), abs(vb)):
                return False
            hits += 1
        return True if hits >= 3 else None
    except Exception:
        return None


# ---- per-topic targets -----------------------------------------------------

def _derivative_target(problem: str) -> sp.Expr | None:
    inner = _DDX.sub("", problem, count=1)
    if inner == problem:  # no d/dx marker; maybe "f(x) = ..." style
        inner = _rhs(problem)
    f = _parse(inner)
    return sp.diff(f, x) if f is not None else None


def _integrand(problem: str) -> sp.Expr | None:
    m = _INT.search(problem)
    return _parse(m.group(1)) if m else None


def _solution_set(eq_latex: str):
    sides = [p for p in eq_latex.split("=") if p.strip()]
    if len(sides) != 2:
        return None
    l, r = _parse(sides[0]), _parse(sides[1])
    if l is None or r is None:
        return None
    try:
        return sp.solveset(sp.Eq(l, r), x, domain=sp.S.Complexes)
    except Exception:
        return None


def _arithmetic_ok(latex: str) -> bool | None:
    """A line of plain numbers ('1 + 1 = 3'): are all its sides equal? None if it
    has a variable, isn't an equation, or won't parse."""
    sides = [p for p in latex.split("=") if p.strip()]
    if len(sides) < 2:
        return None
    vals = [_parse(side) for side in sides]
    if any(v is None or v.free_symbols for v in vals):
        return None
    return all(_equiv(vals[0], v) is True for v in vals[1:])


# ---- main entry ------------------------------------------------------------

def verify(analysis: BoardAnalysis) -> VerifierResult:
    res = VerifierResult(available=AVAILABLE)
    if not AVAILABLE or not analysis.problem:
        res.note = "verifier unavailable or no problem parsed"
        return res

    topic = analysis.topic
    for step in analysis.steps:
        if step.status == StepStatus.UNCLEAR or not step.latex.strip():
            res.line_ok[step.line] = None
            continue

        # Plain arithmetic is checked as written. (Gemini sometimes reads the
        # student's '1 + 1 = 3' as the problem itself, and comparing a line to
        # itself would "prove" it right.)
        ok = _arithmetic_ok(step.latex)
        if ok is not None:
            pass
        elif topic == "derivative":
            target = _derivative_target(analysis.problem)
            student = _parse(_rhs(step.latex))
            if target is not None and student is not None:
                ok = _equiv(student, target)
        elif topic == "integral":
            integrand = _integrand(analysis.problem)
            student = _parse(_rhs(step.latex))
            if integrand is not None and student is not None:
                ok = _equiv(sp.diff(student, x), integrand)   # d/dx of their answer == integrand (ignores +C)
        elif topic == "algebra" and "=" in analysis.problem and "=" in step.latex:
            s0, s1 = _solution_set(analysis.problem), _solution_set(step.latex)
            if s0 is not None and s1 is not None and s0 != sp.S.EmptySet:   # no solutions: nothing to compare
                try:
                    ok = bool(sp.simplify(s0) == sp.simplify(s1))
                except Exception:
                    ok = None
        elif topic == "trig" and "=" in step.latex:
            sides = [p for p in step.latex.split("=") if p.strip()]
            if len(sides) >= 2:
                l, r = _parse(sides[0]), _parse(sides[-1])
                if l is not None and r is not None:
                    ok = _equiv(l, r)
        res.line_ok[step.line] = ok

    fe = analysis.first_error
    if fe is not None and res.line_ok.get(fe.line) is True:
        res.veto_line = fe.line
        res.note = f"SymPy: line {fe.line} is equivalent to a correct step; vetoing Gemini's flag"

    for step in analysis.steps:
        if step.status == StepStatus.OK and res.line_ok.get(step.line) is False:
            res.disagreements.append(f"line {step.line}: Gemini ok, SymPy says not equivalent")
    return res
