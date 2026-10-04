"""Shared data shapes for the brain.

Contract 2 (Gemini -> brain) lives here as pydantic models so that the JSON
schema we hand Gemini, the parser, and the rest of the pipeline all agree.
See docs/GAMEPLAN.md "Contracts".
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class StepStatus(str, Enum):
    OK = "ok"
    WRONG_RULE = "wrong_rule"      # e.g. quotient rule where product rule applies
    MISAPPLIED = "misapplied"      # right rule, applied incorrectly (sign, missing term)
    ARITHMETIC = "arithmetic"      # calculation / algebra slip
    UNCLEAR = "unclear"            # can't read it; never spoken about


Topic = Literal["derivative", "integral", "algebra", "trig", "other"]
Mood = Literal["idle", "listening", "thinking", "talking", "happy", "confused"]

# Gemini bounding box: [ymin, xmin, ymax, xmax] on a 0..1000 scale.
Box = list[int]


class Step(BaseModel):
    line: int = Field(description="1-based line number, top to bottom, as written on the board.")
    latex: str = Field(description="The line as written, in LaTeX. Transcribe, do not correct.")
    status: StepStatus
    rule_used: Optional[str] = Field(
        default=None,
        description="Short snake_case name of the rule the student applied on this line, if any "
        "(product_rule, quotient_rule, chain_rule, power_rule, u_substitution, "
        "integration_by_parts, quadratic_formula, pythagorean_identity, ...).",
    )
    rule_expected: Optional[str] = Field(
        default=None,
        description="Rule that actually applies here, same naming. Internal only; never spoken.",
    )
    box: Box = Field(
        description="Bounding box of this line as [ymin, xmin, ymax, xmax], each 0..1000.",
    )
    note: Optional[str] = Field(
        default=None,
        description="One sentence, internal: what exactly is wrong. May name the fix. Never spoken.",
    )

    @field_validator("box")
    @classmethod
    def _box_shape(cls, v: Box) -> Box:
        if len(v) != 4:
            raise ValueError("box must be [ymin, xmin, ymax, xmax]")
        return [max(0, min(1000, int(x))) for x in v]


class BoardAnalysis(BaseModel):
    board_text: str = Field(description="Everything legible on the board, plain text, top to bottom.")
    problem: str = Field(description="The problem being solved, in LaTeX. Empty string if none.")
    topic: Topic
    board_complete: bool = Field(
        description="False if the student is clearly mid-line (trailing operator, half a symbol, "
        "hand in frame). When false, do not flag anything.",
    )
    steps: list[Step]
    first_error_line: Optional[int] = Field(
        default=None,
        description="Line number of the first non-ok, non-unclear step, else null.",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="How sure you are of the verdict overall.")
    nudge: str = Field(
        description="What the otter says. One short sentence. May name the line number and the KIND "
        "of slip (rule choice / how the rule was applied / arithmetic). MUST NOT name the "
        "correct rule or write any corrected math. Empty string if nothing to flag.",
    )
    mood: Mood

    @property
    def first_error(self) -> Optional[Step]:
        for s in self.steps:
            if s.status not in (StepStatus.OK, StepStatus.UNCLEAR):
                return s
        return None


# ---- Contract 1: brain -> ESP32 ------------------------------------------

class RobotCommand(BaseModel):
    action: Literal["face", "mouth", "look", "laser", "home"]
    state: Optional[Mood] = None
    level: Optional[float] = None
    pan: Optional[float] = None
    tilt: Optional[float] = None
    on: Optional[bool] = None


# ---- Contract 3: brain <-> app ------------------------------------------

class Nudge(BaseModel):
    event: Literal["nudge"] = "nudge"
    text: str
    line: Optional[int]
    kind: Optional[StepStatus]
    mood: Mood


class SessionSummary(BaseModel):
    event: Literal["summary"] = "summary"
    checks: int
    mistakes_by_kind: dict[str, int]
    one_to_review: Optional[str]
    duration_s: float
