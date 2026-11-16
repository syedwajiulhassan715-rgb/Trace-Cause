package dev.tracecause.faults;

import java.util.Random;

/** Holds the active fault for this service. Thread-safe; swapped atomically by the admin endpoint. */
public class FaultState {

    private volatile Fault fault = Fault.NONE;
    private Random random = new Random(0);

    public Fault current() {
        return fault;
    }

    public synchronized void set(Fault next) {
        random = new Random(next.seed());
        fault = next;
    }

    public void clear() {
        set(Fault.NONE);
    }

    /** One seeded coin flip per request: true means this request should fail. */
    public boolean shouldFail() {
        double rate = fault.errorRate();
        if (rate <= 0) {
            return false;
        }
        synchronized (this) {
            return random.nextDouble() < rate;
        }
    }
}
