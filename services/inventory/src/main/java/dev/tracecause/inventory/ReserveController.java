package dev.tracecause.inventory;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReserveController {

    record ReserveRequest(String sku, int quantity) {
    }

    record ReserveResponse(String sku, long unitPriceCents) {
    }

    private final StockStore store;

    public ReserveController(StockStore store) {
        this.store = store;
    }

    @PostMapping("/reserve")
    public ResponseEntity<ReserveResponse> reserve(@RequestBody ReserveRequest request) {
        return store.reserve(request.sku(), request.quantity())
                .map(price -> ResponseEntity.ok(new ReserveResponse(request.sku(), price)))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
