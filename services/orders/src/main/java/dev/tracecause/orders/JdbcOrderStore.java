package dev.tracecause.orders;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
class JdbcOrderStore implements OrderStore {

    private final JdbcClient jdbc;

    JdbcOrderStore(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public long create(String sku, int quantity) {
        return jdbc.sql("INSERT INTO orders (sku, quantity, status) VALUES (?, ?, 'PENDING') RETURNING id")
                .params(sku, quantity)
                .query(Long.class)
                .single();
    }

    @Override
    public void markConfirmed(long orderId, long amountCents) {
        jdbc.sql("UPDATE orders SET status = 'CONFIRMED', amount_cents = ? WHERE id = ?")
                .params(amountCents, orderId)
                .update();
    }

    @Override
    public void markFailed(long orderId) {
        jdbc.sql("UPDATE orders SET status = 'FAILED' WHERE id = ?").params(orderId).update();
    }
}
