package dev.tracecause.gateway;

import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

class HttpOrdersClient implements OrdersClient {

    private final RestClient http;

    HttpOrdersClient(RestClient http) {
        this.http = http;
    }

    @Override
    public OrderResponse placeOrder(CheckoutRequest request) {
        try {
            return http.post().uri("/orders").body(request).retrieve().body(OrderResponse.class);
        } catch (RestClientException e) {
            throw new DownstreamException("orders", e.getMessage());
        }
    }
}
