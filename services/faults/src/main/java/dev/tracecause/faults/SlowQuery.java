package dev.tracecause.faults;

import org.springframework.jdbc.core.simple.JdbcClient;

/**
 * Slow-query fault: before the real query, run {@code pg_sleep} through the same JdbcClient.
 * The agent records it as an ordinary database client span of this service, so the extra
 * time sits in the database call, not in the service's own code.
 */
public final class SlowQuery {

    private SlowQuery() {
    }

    public static void apply(JdbcClient jdbc, FaultState state) {
        long ms = state.current().slowQueryMs();
        if (ms > 0) {
            jdbc.sql("SELECT 1 FROM pg_sleep(?)").param(ms / 1000.0).query(Integer.class).single();
        }
    }
}
