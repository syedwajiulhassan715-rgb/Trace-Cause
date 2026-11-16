"""Seeded fault schedules for the evaluation.

A schedule is a list of segments played one after another: `gap_s` seconds
of clean traffic, then one fault for `duration_s` seconds.

- incident: a fault lasting 40-60 s. Detectors should alert and ranking should
  name the faulted service.
- blip: a fault lasting 4-10 s. Too short to be an incident; an alert on a blip
  counts as a false alarm. This is what a persistence requirement is meant to ignore.

Magnitudes are drawn log-uniformly, so there are as many small, hard-to-see
faults as large, obvious ones. Tuning and held-out schedules use different seeds.
"""

import math
import random
from dataclasses import dataclass

FAULTS_FOR = {
    "gateway": ("delay", "errors"),  # no database
    "orders": ("delay", "slow_query", "errors"),
    "inventory": ("delay", "slow_query", "errors"),
    "payments": ("delay", "slow_query", "errors"),
}
SERVICES = tuple(sorted(FAULTS_FOR))

INCIDENT_SHARE = 0.7
INCIDENT_S = (40, 60)
BLIP_S = (4, 10)
GAP_S = (45, 60)
MS_RANGE = (2, 200)        # delay and slow query, ms
ERROR_RANGE = (0.02, 0.40)

SETS = {  # name -> (seed, number of segments)
    "tuning": (100, 14),
    "heldout": (200, 20),
}


@dataclass(frozen=True)
class Segment:
    index: int
    kind: str        # "incident" or "blip"
    service: str
    fault: str       # "delay", "slow_query" or "errors"
    magnitude: float  # ms for delay/slow_query, probability for errors
    duration_s: int
    gap_s: int        # clean seconds before the fault

    def fault_kwargs(self) -> dict:
        """Arguments for loadgen.faults.set_fault."""
        key = {"delay": "delay_ms", "slow_query": "slow_query_ms", "errors": "error_rate"}[self.fault]
        value = self.magnitude if self.fault == "errors" else int(self.magnitude)
        return {key: value, "seed": self.index}


def _log_uniform(rng, lo, hi):
    return math.exp(rng.uniform(math.log(lo), math.log(hi)))


def generate(seed: int, n: int) -> list[Segment]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        kind = "incident" if rng.random() < INCIDENT_SHARE else "blip"
        service = rng.choice(SERVICES)
        fault = rng.choice(FAULTS_FOR[service])
        if fault == "errors":
            magnitude = round(_log_uniform(rng, *ERROR_RANGE), 3)
        else:
            magnitude = round(_log_uniform(rng, *MS_RANGE))
        duration = rng.randint(*(INCIDENT_S if kind == "incident" else BLIP_S))
        gap = rng.randint(*GAP_S)
        out.append(Segment(i, kind, service, fault, magnitude, duration, gap))
    return out


def total_seconds(segments: list[Segment], warmup_s: int, tail_s: int) -> int:
    return warmup_s + sum(s.gap_s + s.duration_s for s in segments) + tail_s
