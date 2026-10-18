package dev.tracecause.gateway;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CheckoutController {

    private final OrdersClient orders;

    public CheckoutController(OrdersClient orders) {
        this.orders = orders;
    }

    @PostMapping("/checkout")
    public OrderResponse checkout(@RequestBody CheckoutRequest request) {
        return orders.placeOrder(request);
    }

    @ExceptionHandler(DownstreamException.class)
    public ResponseEntity<Map<String, String>> downstreamFailed(DownstreamException e) {
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(Map.of("failedService", e.service(), "error", e.getMessage()));
    }
}
