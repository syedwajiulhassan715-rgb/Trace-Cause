"""Open-loop load generator: seeded Poisson arrivals of checkout requests against the gateway.

    python -m loadgen.load --rate 20 --duration 60 --seed 1

Open loop means requests are sent on schedule whether or not earlier ones have
finished. A closed loop (wait, then send) would slow down exactly when the
system slows down and hide the latency we want the analyzer to see.
"""

import argparse
import json
import os
import random
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

SKUS = ("SKU-1", "SKU-2", "SKU-3")


@dataclass(frozen=True)
class Request:
    offset_s: float
    sku: str
    quantity: int


def plan(seed, rate, duration_s):
    """The full request schedule, fixed by the seed: same seed, same requests at the same offsets."""
    if rate <= 0:
        raise ValueError("rate must be > 0")
    rng = random.Random(seed)
    out, t = [], rng.expovariate(rate)
    while t < duration_s:
        out.append(Request(t, rng.choice(SKUS), rng.randint(1, 3)))
        t += rng.expovariate(rate)
    return out


def _send(url, req):
    body = json.dumps({"sku": req.sku, "quantity": req.quantity}).encode()
    http_req = urllib.request.Request(url, data=body, method="POST",
                                      headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(http_req, timeout=30) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        status = 0
    return status, (time.perf_counter() - start) * 1000


def run(rate, duration_s, seed, gateway=None, workers=64):
    gateway = gateway or f"http://{os.environ.get('TRACECAUSE_HOST', 'localhost')}:8080"
    url = f"{gateway}/checkout"
    schedule = plan(seed, rate, duration_s)
    futures = []
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for req in schedule:
            wait = req.offset_s - (time.perf_counter() - t0)
            if wait > 0:
                time.sleep(wait)
            futures.append(pool.submit(_send, url, req))
    results = [f.result() for f in futures]
    return summarize(results)


def summarize(results):
    lat = sorted(ms for _, ms in results)
    codes = {}
    for status, _ in results:
        codes[status] = codes.get(status, 0) + 1
    if not lat:
        return {"requests": 0, "status": {}}
    return {
        "requests": len(results),
        "status": dict(sorted(codes.items())),
        "p50_ms": round(statistics.median(lat), 1),
        "p95_ms": round(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 1),
        "max_ms": round(lat[-1], 1),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rate", type=float, default=20, help="mean requests per second")
    parser.add_argument("--duration", type=float, default=60, help="seconds")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--gateway", default=None, help="default http://localhost:8080")
    args = parser.parse_args(argv)
    print(json.dumps(run(args.rate, args.duration, args.seed, args.gateway)))


if __name__ == "__main__":
    main()
