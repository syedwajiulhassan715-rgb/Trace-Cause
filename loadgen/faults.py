"""Set, show and clear faults on the demo services through their /admin/fault endpoint.

    python -m loadgen.faults set inventory --delay-ms 300
    python -m loadgen.faults set payments --slow-query-ms 400
    python -m loadgen.faults set orders --error-rate 0.3 --seed 7
    python -m loadgen.faults show
    python -m loadgen.faults clear            # all services
"""

import argparse
import json
import os
import urllib.request

# Host ports from docker-compose.yml. Override the host with TRACECAUSE_HOST.
SERVICES = {"gateway": 8080, "orders": 8081, "inventory": 8082, "payments": 8083}
MAX_MS = 60_000


def admin_url(service, host=None):
    if service not in SERVICES:
        raise ValueError(f"unknown service {service!r}; expected one of {sorted(SERVICES)}")
    host = host or os.environ.get("TRACECAUSE_HOST", "localhost")
    return f"http://{host}:{SERVICES[service]}/admin/fault"


def fault_body(delay_ms=0, error_rate=0.0, slow_query_ms=0, seed=0):
    """Validate on the client too, so a bad scenario fails before it touches the stack."""
    if not 0 <= delay_ms <= MAX_MS:
        raise ValueError(f"delay_ms must be in [0, {MAX_MS}]")
    if not 0.0 <= error_rate <= 1.0:
        raise ValueError("error_rate must be in [0, 1]")
    if not 0 <= slow_query_ms <= MAX_MS:
        raise ValueError(f"slow_query_ms must be in [0, {MAX_MS}]")
    return {"delayMs": int(delay_ms), "errorRate": float(error_rate),
            "slowQueryMs": int(slow_query_ms), "seed": int(seed)}


def _call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def set_fault(service, **kwargs):
    return _call("PUT", admin_url(service), fault_body(**kwargs))


def get_fault(service):
    return _call("GET", admin_url(service))


def clear_fault(service):
    return _call("DELETE", admin_url(service))


def clear_all():
    return {s: clear_fault(s) for s in SERVICES}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_set = sub.add_parser("set", help="inject a fault into one service")
    p_set.add_argument("service", choices=sorted(SERVICES))
    p_set.add_argument("--delay-ms", type=int, default=0)
    p_set.add_argument("--error-rate", type=float, default=0.0)
    p_set.add_argument("--slow-query-ms", type=int, default=0)
    p_set.add_argument("--seed", type=int, default=0)
    p_show = sub.add_parser("show", help="print the active fault per service")
    p_show.add_argument("service", nargs="?", choices=sorted(SERVICES))
    p_clear = sub.add_parser("clear", help="remove faults (all services if none given)")
    p_clear.add_argument("service", nargs="?", choices=sorted(SERVICES))
    args = parser.parse_args(argv)

    if args.cmd == "set":
        print(json.dumps(set_fault(args.service, delay_ms=args.delay_ms, error_rate=args.error_rate,
                                   slow_query_ms=args.slow_query_ms, seed=args.seed)))
    elif args.cmd == "show":
        for s in [args.service] if args.service else SERVICES:
            print(f"{s:10s} {json.dumps(get_fault(s))}")
    else:
        if args.service:
            print(json.dumps(clear_fault(args.service)))
        else:
            clear_all()
            print("cleared all")


if __name__ == "__main__":
    main()
