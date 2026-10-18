package dev.tracecause.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderStore store;
    private final InventoryClient inventory;
    private final PaymentsClient payments;

    public OrderService(OrderStore store, InventoryClient inventory, PaymentsClient payments) {
        this.store = store;
        this.inventory = inventory;
        this.payments = payments;
    }

    public OrderResponse place(OrderRequest request) {
        long orderId = store.create(request.sku(), request.quantity());
        try {
            long unitPriceCents = inventory.reserve(request.sku(), request.quantity());
            long amountCents = unitPriceCents * request.quantity();
            payments.charge(orderId, amountCents);
            store.markConfirmed(orderId, amountCents);
            return new OrderResponse(orderId, "CONFIRMED", amountCents);
        } catch (DownstreamException e) {
            store.markFailed(orderId);
            throw e;
        }
    }
}
