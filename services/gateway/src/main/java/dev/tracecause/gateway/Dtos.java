package dev.tracecause.gateway;

record CheckoutRequest(String sku, int quantity) {
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
