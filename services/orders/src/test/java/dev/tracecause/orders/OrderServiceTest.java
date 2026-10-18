package dev.tracecause.orders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

class OrderServiceTest {

    /** In-memory store so the test needs no database. */
    static class FakeStore implements OrderStore {
        final Map<Long, String> status = new HashMap<>();
        final Map<Long, Long> amount = new HashMap<>();
        long nextId = 1;

        @Override
        public long create(String sku, int quantity) {
            status.put(nextId, "PENDING");
            return nextId++;
        }

        @Override
        public void markConfirmed(long orderId, long amountCents) {
            status.put(orderId, "CONFIRMED");
            amount.put(orderId, amountCents);
        }

        @Override
        public void markFailed(long orderId) {
            status.put(orderId, "FAILED");
        }
    }

    @Test
    void confirmsOrderWithPriceTimesQuantity() {
        FakeStore store = new FakeStore();
        long[] charged = new long[1];
        OrderService service = new OrderService(store,
                (sku, qty) -> 250L,
                (orderId, amountCents) -> charged[0] = amountCents);

        OrderResponse response = service.place(new OrderRequest("SKU-1", 3));

        assertThat(response).isEqualTo(new OrderResponse(1, "CONFIRMED", 750));
        assertThat(charged[0]).isEqualTo(750);
        assertThat(store.status.get(1L)).isEqualTo("CONFIRMED");
    }

    @Test
    void marksOrderFailedWhenInventoryFails() {
        FakeStore store = new FakeStore();
        OrderService service = new OrderService(store,
                (sku, qty) -> {
                    throw new DownstreamException("inventory", "unavailable");
                },
                (orderId, amountCents) -> {
                    throw new AssertionError("payments must not be called");
                });

        assertThatThrownBy(() -> service.place(new OrderRequest("SKU-1", 1)))
                .isInstanceOf(DownstreamException.class);
        assertThat(store.status.get(1L)).isEqualTo("FAILED");
    }

    @Test
    void marksOrderFailedWhenPaymentsFails() {
        FakeStore store = new FakeStore();
        OrderService service = new OrderService(store,
                (sku, qty) -> 100L,
                (orderId, amountCents) -> {
                    throw new DownstreamException("payments", "declined");
                });

        assertThatThrownBy(() -> service.place(new OrderRequest("SKU-1", 1)))
                .isInstanceOf(DownstreamException.class)
                .extracting(e -> ((DownstreamException) e).service())
                .isEqualTo("payments");
        assertThat(store.status.get(1L)).isEqualTo("FAILED");
    }
}
