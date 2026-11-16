"""Score one detector's alerts and one ranker against a recorded fault timeline.

Matching rules (all times in seconds):
- A 10 s window [w, w+10) belongs to a segment if it overlaps
  [start_s, end_s + lag_s). The lag allows for detectors that need several
  windows of evidence and for the fault's last requests finishing.
- An incident is detected if any alert window belongs to it. Detection delay
  is the end of the first such window minus the fault start: the earliest
  moment that window's data could exist.
- An alert on a blip is a false alarm. Alerts in clean time (outside every
  segment and its lag) are false alarms too, counted as episodes: adjacent
  alerted windows are one episode, as an on-call engineer would see them.
- precision = detected incidents / (detected incidents + blip alarms + clean episodes)
- Root cause: the ranker gets the incident's alert windows. top-k counts a
  missed incident as wrong; top-k "detected" only looks at detected incidents.
"""

import statistics
from dataclasses import dataclass

WINDOW_S = 10


@dataclass(frozen=True)
class SetResult:
    incidents: int
    detected: int
    recall: float
    delays_s: list
    median_delay_s: float | None
    blips: int
    blip_alarms: int
    clean_hours: float
    clean_episodes: int
    precision: float
    f1: float
    top1: float
    top3: float
    top1_detected: float
    top3_detected: float

    @property
    def clean_alarms_per_hour(self) -> float:
        return self.clean_episodes / self.clean_hours if self.clean_hours else 0.0


def _overlaps(w, start, end):
    return w < end and w + WINDOW_S > start


def alarm_episodes(window_starts) -> int:
    episodes, prev = 0, None
    for w in sorted(set(window_starts)):
        if prev is None or w - prev > WINDOW_S:
            episodes += 1
        prev = w
    return episodes


def evaluate_set(segments, alerts, ranker, clean_start_s, clean_end_s, lag_s=20) -> SetResult:
    """segments: dicts with kind, service, start_s, end_s. alerts: (service, window_start_s) pairs.
    ranker: callable(set of incident window starts) -> list of services, best first."""
    alert_windows = sorted({w for _, w in alerts})
    spans = [(s["start_s"], s["end_s"] + lag_s) for s in segments]

    incidents = [s for s in segments if s["kind"] == "incident"]
    blips = [s for s in segments if s["kind"] == "blip"]

    delays, top1, top3 = [], 0, 0
    for s in incidents:
        hit = [w for w in alert_windows if _overlaps(w, s["start_s"], s["end_s"] + lag_s)]
        if not hit:
            continue
        delays.append(round(hit[0] + WINDOW_S - s["start_s"], 3))
        ranking = ranker(set(hit))
        top1 += ranking[:1] == [s["service"]]
        top3 += s["service"] in ranking[:3]

    blip_alarms = sum(any(_overlaps(w, s["start_s"], s["end_s"] + lag_s) for w in alert_windows) for s in blips)
    clean = [w for w in alert_windows
             if clean_start_s <= w < clean_end_s and not any(_overlaps(w, a, b) for a, b in spans)]
    episodes = alarm_episodes(clean)

    busy = sum(min(b, clean_end_s) - max(a, clean_start_s) for a, b in spans if b > clean_start_s and a < clean_end_s)
    clean_hours = (clean_end_s - clean_start_s - busy) / 3600

    detected = len(delays)
    recall = detected / len(incidents) if incidents else 0.0
    false_alarms = blip_alarms + episodes
    precision = detected / (detected + false_alarms) if detected + false_alarms else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    n = len(incidents) or 1
    return SetResult(
        incidents=len(incidents), detected=detected, recall=recall,
        delays_s=delays, median_delay_s=statistics.median(delays) if delays else None,
        blips=len(blips), blip_alarms=blip_alarms,
        clean_hours=clean_hours, clean_episodes=episodes,
        precision=precision, f1=f1,
        top1=top1 / n, top3=top3 / n,
        top1_detected=top1 / detected if detected else 0.0,
        top3_detected=top3 / detected if detected else 0.0,
    )
