package dev.tracecause.faults;

/**
 * The fault currently injected into one service.
 *
 * @param delayMs     extra time spent inside the service on every request (shows up as self-time)
 * @param errorRate   probability in [0, 1] that a request is answered with HTTP 500
 * @param slowQueryMs extra database time per query, issued as a real {@code pg_sleep} statement
 * @param seed        seeds the error coin flips so a scenario can be replayed
 */
public record Fault(long delayMs, double errorRate, long slowQueryMs, long seed) {

    public static final Fault NONE = new Fault(0, 0, 0, 0);

    static final long MAX_MS = 60_000;

    public Fault {
        if (delayMs < 0 || delayMs > MAX_MS) {
            throw new IllegalArgumentException("delayMs must be in [0, " + MAX_MS + "]");
        }
        if (!(errorRate >= 0 && errorRate <= 1)) {
            throw new IllegalArgumentException("errorRate must be in [0, 1]");
        }
        if (slowQueryMs < 0 || slowQueryMs > MAX_MS) {
            throw new IllegalArgumentException("slowQueryMs must be in [0, " + MAX_MS + "]");
        }
    }
}
