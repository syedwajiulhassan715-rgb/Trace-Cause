package dev.tracecause.orders;

interface OrderStore {

    long create(String sku, int quantity);

    void markConfirmed(long orderId, long amountCents);

    void markFailed(long orderId);
}

@FunctionalInterface
interface InventoryClient {

    /** Reserves stock and returns the unit price in cents. */
    long reserve(String sku, int quantity);
}

@FunctionalInterface
interface PaymentsClient {

    void charge(long orderId, long amountCents);
}

record OrderRequest(String sku, int quantity) {
}

record OrderResponse(long orderId, String status, long amountCents) {
}

class DownstreamException extends RuntimeException {

    private final String service;

    DownstreamException(String service, String message) {
        super(message);
        this.service = service;
    }

    String service() {
        return service;
    }
}
