"""Run the evaluation: every scenario through arm (a) locally and arms (b)+(c) through the services."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from mimamori_common.llm import ModelClient

from .arm_a import ArmA
from .arm_bc import ARM_B, ARM_C, ServiceArms
from .judge import Judgement, judge_one
from .params import SimParams
from .personas import QuestionIndex, RolePlayer, ScriptedRolePlayer
from .scenarios import Scenario
from .teller import ArmOutcome

ARM_LABELS = {
    "a_counter_check": "(a) today's counter check",
    "b_statistics": "(b) statistics only",
    "c_mimamori": "(c) full Mimamori",
}
ARMS = list(ARM_LABELS)


@dataclass
class ScenarioResult:
    scenario: Scenario
    arms: dict[str, ArmOutcome | None]
    judgements: list[Judgement] = field(default_factory=list)


@dataclass
class RunResult:
    params: SimParams
    synthetic: list[ScenarioResult] = field(default_factory=list)
    heldout: list[ScenarioResult] = field(default_factory=list)
    sweep: dict[int, list[ScenarioResult]] = field(default_factory=dict)  # arm (a) threshold sweep, synthetic set
    meta: dict = field(default_factory=dict)


async def run_scenarios(scenarios: list[Scenario], params: SimParams, index: QuestionIndex,
                        services: ServiceArms | None, role: RolePlayer, judge: ModelClient | None) -> list[ScenarioResult]:
    arm_a = ArmA(index, params)
    out: list[ScenarioResult] = []
    for sc in scenarios:
        a = await arm_a.run(sc, role)
        b = c = None
        if services is not None:
            b, c = await services.run(sc, role)
        arms = {"a_counter_check": a, ARM_B: b, ARM_C: c}
        res = ScenarioResult(sc, arms)
        if judge is not None:
            for o in (a, c):
                if o is not None:
                    j = await judge_one(judge, sc, o)
                    if j is not None:
                        res.judgements.append(j)
        out.append(res)
    return out


async def threshold_sweep(scenarios: list[Scenario], params: SimParams, index: QuestionIndex,
                          thresholds: list[int]) -> dict[int, list[ScenarioResult]]:
    """Arm (a) only, scripted customers (deterministic), at several amount thresholds."""
    sweep = {}
    for t in thresholds:
        p = SimParams(amount_threshold_jpy=t, follow_p=params.follow_p, max_turns=params.max_turns, seed=params.seed)
        sweep[t] = await run_scenarios(scenarios, p, index, None, ScriptedRolePlayer(), None)
    return sweep


# --------------------------------------------------------------------------- metrics


@dataclass
class ArmSummary:
    arm: str
    scam_n: int = 0
    scam_caught: int = 0
    scam_missed: int = 0
    missed_not_engaged: int = 0  # the arm never looked (below threshold, no alert, no case)
    missed_no_flag: int = 0  # looked, nothing raised
    missed_not_acted: int = 0  # flag raised, teller did not act (shared assumption)
    legit_n: int = 0
    legit_false_pause: int = 0
    yen_lost: int = 0  # scam amounts that went through
    yen_held_legit: int = 0  # legit amounts paused
    turns_to_pause: list[int] = field(default_factory=list)
    errors: int = 0
    judged: int = 0
    judge_unreasonable: int = 0
    wording_problems: int = 0
    judge_errors: int = 0

    @property
    def mean_turns_to_pause(self) -> float | None:
        return sum(self.turns_to_pause) / len(self.turns_to_pause) if self.turns_to_pause else None


def classify_miss(o: ArmOutcome) -> str:
    if o.error:
        return "error"
    if not o.engaged:
        return "not_engaged"
    if o.flag_ever:
        return "not_acted"
    return "no_flag"


def summarize(results: list[ScenarioResult], arm: str) -> ArmSummary:
    s = ArmSummary(arm)
    for r in results:
        o = r.arms.get(arm)
        if o is None:
            continue
        sc = r.scenario
        if o.error:
            s.errors += 1
        if sc.ground_truth == "scam":
            s.scam_n += 1
            if o.paused:
                s.scam_caught += 1
                if o.paused_at_turn is not None:
                    s.turns_to_pause.append(o.paused_at_turn)
            else:
                s.scam_missed += 1
                s.yen_lost += sc.amount_jpy
                kind = classify_miss(o)
                if kind == "not_engaged":
                    s.missed_not_engaged += 1
                elif kind == "no_flag":
                    s.missed_no_flag += 1
                elif kind == "not_acted":
                    s.missed_not_acted += 1
        else:
            s.legit_n += 1
            if o.paused:
                s.legit_false_pause += 1
                s.yen_held_legit += sc.amount_jpy
        for j in r.judgements:
            if j.arm != arm:
                continue
            if j.error:
                s.judge_errors += 1
                continue
            s.judged += 1
            s.judge_unreasonable += 0 if j.decision_reasonable else 1
            s.wording_problems += len(j.wording_problems)
    return s


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
