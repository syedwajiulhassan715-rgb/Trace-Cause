"""Record one evaluation set against the running stack.

    docker compose down -v && docker compose up -d --build     # start from a clean span store
    python -m eval.run tuning
    python -m eval.run heldout

Plays the set's seeded schedule under seeded open-loop load, writes the actual
fault start/end times to eval/data/<set>.timeline.json and copies the
analyzer's span database to eval/data/<set>.db. Evaluation then runs offline
on those two files (python -m eval.evaluate), as often as needed.
"""

import argparse
import json
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import asdict
from pathlib import Path

from loadgen import faults, load

from .scenarios import SETS, generate, total_seconds

DATA = Path(__file__).parent / "data"
RATE = 10          # requests per second
WARMUP_S = 70      # JVM warm-up plus enough clean windows for a first baseline
TAIL_S = 40        # clean traffic after the last fault, so its windows close
FLUSH_S = 20       # let the last spans reach the analyzer before copying the store


def _wait_for_analyzer():
    for _ in range(60):
        try:
            with urllib.request.urlopen("http://localhost:8000/health", timeout=2):
                return
        except OSError:
            time.sleep(2)
    sys.exit("analyzer is not reachable on localhost:8000; is the stack up?")


def record(name: str):
    seed, n = SETS[name]
    segments = generate(seed, n)
    duration = total_seconds(segments, WARMUP_S, TAIL_S)
    DATA.mkdir(exist_ok=True)
    _wait_for_analyzer()
    faults.clear_all()
    print(f"[{name}] {n} segments, {duration} s of load at {RATE} req/s", flush=True)

    summary = {}
    t0 = time.time()
    loader = threading.Thread(target=lambda: summary.update(load.run(RATE, duration, seed)))
    loader.start()

    def wait_until(offset_s):
        time.sleep(max(0.0, t0 + offset_s - time.time()))

    timeline, offset = [], WARMUP_S
    try:
        for seg in segments:
            offset += seg.gap_s
            wait_until(offset)
            faults.set_fault(seg.service, **seg.fault_kwargs())
            start = time.time()
            offset += seg.duration_s
            wait_until(offset)
            faults.clear_fault(seg.service)
            end = time.time()
            timeline.append({**asdict(seg), "start_s": round(start, 3), "end_s": round(end, 3)})
            print(f"[{name}] {seg.index:2d} {seg.kind:8s} {seg.service:9s} {seg.fault:10s} "
                  f"{seg.magnitude:>7} for {end - start:4.1f} s", flush=True)
    finally:
        faults.clear_all()
    loader.join()
    time.sleep(FLUSH_S)

    db = DATA / f"{name}.db"
    subprocess.run(["docker", "compose", "cp", "analyzer:/data/spans.db", str(db)], check=True)
    (DATA / f"{name}.timeline.json").write_text(json.dumps({
        "set": name, "seed": seed, "rate": RATE, "started_s": round(t0, 3),
        "ended_s": round(t0 + duration, 3), "load": summary, "segments": timeline,
    }, indent=2))
    print(f"[{name}] done: {db} ({db.stat().st_size // 1_000_000} MB), load {summary}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("set", choices=sorted(SETS))
    record(parser.parse_args(argv).set)


if __name__ == "__main__":
    main()
