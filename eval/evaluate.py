"""Offline evaluation of both detectors and the root-cause ranking on recorded sets.

    python -m eval.evaluate          # needs eval/data/{tuning,heldout}.{db,timeline.json}

1. For each set, rebuild the analyzer's 10 s buckets from the recorded spans and
   score them with the analyzer's own code (no copies of the logic here).
2. Tuning set only: grid-search each detector's parameters, pick the best F1
   (ties: better top-1, then shorter delay, then the smaller parameters).
3. Held-out set: apply the chosen parameters unchanged and report.
4. Ranking ablation on held-out: the same incident windows ranked by total
   latency and total error rate instead of self-time and own errors, and the
   random-ranking baseline (1 of 4 services: 25 % top-1, 75 % top-3).

Writes eval/results.md and eval/results.json.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analyzer"))

from tracecause.buckets import bucketize  # noqa: E402
from tracecause.detect import PersistenceDetector, Signal, ThresholdDetector, score_series  # noqa: E402
from tracecause.rank import call_graph, rank  # noqa: E402
from tracecause.store import SpanStore  # noqa: E402

from .metrics import evaluate_set  # noqa: E402
from .run import WARMUP_S  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
S = 1_000_000_000

# Ablation: what ranking would see without self-time and own-error attribution.
RAW_SIGNALS = (Signal("total_ms", "p50_ms", 1.0), Signal("error_rate", "error_rate", 0.02))

GRID = {
    "threshold": [ThresholdDetector(k=k) for k in (2, 3, 4, 5, 6, 8, 10)],
    "persistence": [PersistenceDetector(k=k, windows=w) for k in (2, 3, 4, 5, 6, 8) for w in (2, 3, 4)],
}


def params(det) -> str:
    return f"k={det.k}" + (f", windows={det.windows}" if hasattr(det, "windows") else "")


class Recording:
    def __init__(self, name: str):
        self.name = name
        self.timeline = json.loads((DATA / f"{name}.timeline.json").read_text(encoding="utf-8"))
        store = SpanStore(str(DATA / f"{name}.db"))
        t0, t1 = self.timeline["started_s"], self.timeline["ended_s"]
        spans = store.spans_between(int((t0 - 60) * S), int((t1 + 120) * S))
        self.span_count = len(spans)
        buckets = bucketize(spans, now_ns=int((t1 + 3600) * S))
        self.edges = call_graph(spans)
        self.scores = score_series(buckets)
        self.raw_scores = score_series(buckets, signals=RAW_SIGNALS)
        self.clean_start_s = t0 + WARMUP_S
        self.clean_end_s = t1

    def evaluate(self, detector, scores=None):
        """Alerts always come from the real detector signals; `scores` only changes the ranking input."""
        alerts = [(a.service, a.window_start_ns // S) for a in detector.detect(self.scores)]
        rank_scores = scores if scores is not None else self.scores

        def ranker(windows):
            return [c.service for c in rank(rank_scores, {w * S for w in windows}, self.edges)]

        return evaluate_set(self.timeline["segments"], alerts, ranker, self.clean_start_s, self.clean_end_s)

    def per_incident(self, detector):
        """For the report: which incidents were found, and what ranked first."""
        alerts = [(a.service, a.window_start_ns // S) for a in detector.detect(self.scores)]
        windows = sorted({w for _, w in alerts})
        rows = []
        for seg in self.timeline["segments"]:
            hit = {w for w in windows if w < seg["end_s"] + 20 and w + 10 > seg["start_s"]}
            top = rank(self.scores, {w * S for w in hit}, self.edges)[:1] if hit else []
            rows.append((seg, bool(hit), top[0].service if top else None))
        return rows


def choose(rec: Recording, family: str):
    def key(item):
        det, r = item
        return (r.f1, r.top1, -(r.median_delay_s or 1e9), -det.k, -getattr(det, "windows", 0))
    results = [(det, rec.evaluate(det)) for det in GRID[family]]
    return max(results, key=key), results


def pct(x):
    return f"{100 * x:.0f} %"


def row(name, det, r):
    delay = f"{r.median_delay_s:.0f} s" if r.median_delay_s is not None else "-"
    return (f"| {name} | {params(det)} | {r.detected}/{r.incidents} ({pct(r.recall)}) | {pct(r.precision)} | "
            f"{r.f1:.2f} | {r.blip_alarms}/{r.blips} | {r.clean_episodes} ({r.clean_alarms_per_hour:.1f}/h) | "
            f"{delay} | {pct(r.top1)} | {pct(r.top3)} | {pct(r.top1_detected)} |")


HEADER = ("| Detector | Parameters | Incidents found | Precision | F1 | Blips alerted | Clean-time alarms | "
          "Median delay | Top-1 | Top-3 | Top-1 of found |\n|---|---|---|---|---|---|---|---|---|---|---|")


def write_readme_results(chosen, held, raw, heldout: Recording):
    """Replace the README's RESULTS block, so its numbers always come from this run."""
    readme = HERE.parent / "README.md"
    start, end = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
    text = readme.read_text(encoding="utf-8")
    if start not in text or end not in text:
        return
    t = heldout.timeline
    n_inc = sum(s["kind"] == "incident" for s in t["segments"])
    block = [
        start,
        f"Held-out set: {n_inc} incidents and {len(t['segments']) - n_inc} blips, "
        f"{(t['ended_s'] - t['started_s']) / 60:.0f} min at {t['rate']} req/s. Parameters were tuned on a "
        "separate tuning set only. Generated by `python -m eval.evaluate`; details in "
        "[`eval/results.md`](eval/results.md).",
        "",
        "| Detector | Parameters | Incidents found | Precision | F1 | Blips alerted | Clean-time alarms | "
        "Median delay | Top-1 | Top-1 of found |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for f in GRID:
        r = held[f]
        delay = f"{r.median_delay_s:.0f} s" if r.median_delay_s is not None else "-"
        block.append(f"| {f} | {params(chosen[f])} | {r.detected}/{r.incidents} | {pct(r.precision)} | {r.f1:.2f} | "
                     f"{r.blip_alarms}/{r.blips} | {r.clean_episodes} ({r.clean_alarms_per_hour:.1f}/h) | {delay} | "
                     f"{pct(r.top1)} | {pct(r.top1_detected)} |")
    block += ["", "Ranking ablation on the same held-out incidents (top-1 of found):", "",
              "| Detector | Self-time + own errors | Total latency + total errors | Random |", "|---|---|---|---|"]
    for f in GRID:
        block.append(f"| {f} | {pct(held[f].top1_detected)} | {pct(raw[f].top1_detected)} | 25 % |")
    block.append(end)
    before, rest = text.split(start, 1)
    after = rest.split(end, 1)[1]
    readme.write_text(before + "\n".join(block) + after, encoding="utf-8")


def main():
    tuning, heldout = Recording("tuning"), Recording("heldout")
    chosen, grids = {}, {}
    for family in GRID:
        (det, _), results = choose(tuning, family)
        chosen[family], grids[family] = det, results

    held = {f: heldout.evaluate(d) for f, d in chosen.items()}
    tuned = {f: tuning.evaluate(d) for f, d in chosen.items()}
    raw = {f: heldout.evaluate(d, scores=heldout.raw_scores) for f, d in chosen.items()}

    lines = ["# Evaluation results", "",
             "Generated by `python -m eval.evaluate` from recordings made with `python -m eval.run`.",
             "Do not edit by hand.", ""]
    for rec in (tuning, heldout):
        t = rec.timeline
        n_inc = sum(s["kind"] == "incident" for s in t["segments"])
        lines.append(f"- **{rec.name}**: seed {t['seed']}, {len(t['segments'])} segments ({n_inc} incidents, "
                     f"{len(t['segments']) - n_inc} blips), {t['ended_s'] - t['started_s']:.0f} s at {t['rate']} req/s, "
                     f"{rec.span_count} spans, load {t['load']}")
    lines += ["", "Parameters were chosen on the tuning set only (best F1), then applied unchanged to the held-out set.",
              "", "## Held-out results", "", HEADER]
    lines += [row(f, chosen[f], held[f]) for f in GRID]
    lines += ["", "## Root-cause ranking ablation (held-out)", "",
              "Same incident windows; only the signals given to the ranker change.", "",
              "| Detector | Ranked on | Top-1 of found | Top-3 of found |", "|---|---|---|---|"]
    for f in GRID:
        lines.append(f"| {f} | self-time, DB time, own errors | {pct(held[f].top1_detected)} | {pct(held[f].top3_detected)} |")
        lines.append(f"| {f} | total latency, total errors | {pct(raw[f].top1_detected)} | {pct(raw[f].top3_detected)} |")
    lines.append("| - | random order of 4 services | 25 % | 75 % |")

    lines += ["", "## Held-out incidents", "",
              "| # | Kind | Service | Fault | Magnitude | Threshold found / rank 1 | Persistence found / rank 1 |",
              "|---|---|---|---|---|---|---|"]
    per = {f: heldout.per_incident(chosen[f]) for f in GRID}
    for i, (seg, _, _) in enumerate(per["threshold"]):
        cells = []
        for f in GRID:
            _, hit, top = per[f][i]
            cells.append(f"{'yes' if hit else 'no'} / {top or '-'}")
        lines.append(f"| {seg['index']} | {seg['kind']} | {seg['service']} | {seg['fault']} | {seg['magnitude']} | "
                     f"{cells[0]} | {cells[1]} |")

    lines += ["", "## Tuning set (for reference)", "", HEADER]
    lines += [row(f, chosen[f], tuned[f]) for f in GRID]
    lines += ["", "### Full tuning grid", "", HEADER]
    for f in GRID:
        lines += [row(f, d, r) for d, r in grids[f]]

    (HERE / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_readme_results(chosen, held, raw, heldout)
    (HERE / "results.json").write_text(json.dumps({
        "chosen": {f: params(d) for f, d in chosen.items()},
        "heldout": {f: asdict(r) for f, r in held.items()},
        "heldout_ablation_raw_signals": {f: asdict(r) for f, r in raw.items()},
        "tuning": {f: asdict(r) for f, r in tuned.items()},
    }, indent=2), encoding="utf-8")
    print((HERE / "results.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
