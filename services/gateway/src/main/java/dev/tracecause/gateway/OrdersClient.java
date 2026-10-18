package dev.tracecause.gateway;

public interface OrdersClient {

    OrderResponse placeOrder(CheckoutRequest request);
}
