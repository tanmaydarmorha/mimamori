"""Run parameters. Everything the three arms share, or that a reader must be told, is here."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

# Held-out cut-off (CR 16, CR 28): playbooks used must be published before T, held-out cases on or after T.
T = date(2026, 4, 1)

TELLER_ID = "sim-teller"
MANAGER_ID = "sim-manager"


@dataclass(frozen=True)
class SimParams:
    # Arm (a): today's counter check applies only to a transfer or withdrawal at or above this amount.
    # No national figure is published (R1 gaps); 1,000,000 is a stated parameter, equal to the bank's own
    # large-transfer threshold. The report sweeps it.
    amount_threshold_jpy: int = 1_000_000
    # THE shared teller-behaviour assumption (one for all three arms): the teller asks the arm's questions,
    # and when the arm raises its escalation flag the teller pauses if `acts_on_flag`, otherwise carries on
    # and releases. `follow_p` = chance a given teller acts on a flag; 1.0 = always. The same per-scenario
    # draw is used for every arm (common random numbers).
    follow_p: float = 1.0
    # Questions a teller can ask per transaction, the same cap for every arm.
    max_turns: int = 6
    seed: int = 20261013
    cutoff: date = T

    def u(self, scenario_id: str) -> float:
        """Common random number in [0, 1) per scenario: identical across arms."""
        digest = hashlib.sha256(f"{self.seed}:{scenario_id}".encode()).digest()
        return int.from_bytes(digest[:8], "big") / 2**64

    def teller_acts(self, scenario_id: str) -> bool:
        return self.u(scenario_id) < self.follow_p
