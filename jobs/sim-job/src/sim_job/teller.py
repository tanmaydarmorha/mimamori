"""The one shared teller-behaviour assumption (decisions.md CR 19).

A teller is not modelled as skilled or unskilled. Each arm supplies (1) the questions the teller asks
and (2) a flag when its own method says "escalate". The teller then behaves identically in every arm:

    asks the arm's questions in order, up to `max_turns`;
    at the first turn the arm's flag is up, pauses if the teller acts on flags (a per-scenario draw that
    is the same in every arm), otherwise carries on;
    after the last question with no pause, clears and releases.

Nothing about the teller changes between arms, so differences in the results come from each arm's flags
and questions only. Every pause here stands for a human decision (a teller pausing, with the police
notified in arm (a)'s routine); the sim logs it with a rationale like any other.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ArmOutcome:
    arm: str  # "a_counter_check" | "b_statistics" | "c_mimamori"
    scenario_id: str
    paused: bool
    paused_at_turn: int | None  # 0 = before any question (statistics alert), n = after n customer replies
    flag_ever: bool  # the arm's flag went up at some point (even if the teller did not act)
    flag_first_turn: int | None
    engaged: bool = True  # False when the arm never engaged (below the amount threshold, no alert, no case)
    questions: list[dict] = field(default_factory=list)  # {"id", "ja", "purpose"} asked, in order
    transcript: list[dict] = field(default_factory=list)  # {"turn_id", "speaker", "text"}
    reasons: list[str] = field(default_factory=list)  # why the flag went up (arm-specific, for the report)
    notes: list[str] = field(default_factory=list)
    risk_level: str | None = None
    case_id: str | None = None
    hold_line_ja: str | None = None
    scoring: str | None = None
    signals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def decide(flag_up: bool, acts_on_flag: bool) -> bool:
    """The teller's pause decision at a turn: pause only if the arm flagged and the teller acts on flags."""
    return flag_up and acts_on_flag
