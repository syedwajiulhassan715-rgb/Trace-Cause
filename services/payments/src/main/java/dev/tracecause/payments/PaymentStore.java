package dev.tracecause.payments;

@FunctionalInterface
public interface PaymentStore {

    /** Persists a captured payment and returns its id. */
    long record(long orderId, long amountCents);
}
