package dev.tracecause.orders;

import dev.tracecause.faults.FaultState;
import dev.tracecause.faults.SlowQuery;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
class JdbcOrderStore implements OrderStore {

    private final JdbcClient jdbc;
    private final FaultState faults;

    JdbcOrderStore(JdbcClient jdbc, FaultState faults) {
        this.jdbc = jdbc;
        this.faults = faults;
    }

    @Override
    public long create(String sku, int quantity) {
        SlowQuery.apply(jdbc, faults);
        return jdbc.sql("INSERT INTO orders (sku, quantity, status) VALUES (?, ?, 'PENDING') RETURNING id")
                .params(sku, quantity)
                .query(Long.class)
                .single();
    }

    @Override
    public void markConfirmed(long orderId, long amountCents) {
        SlowQuery.apply(jdbc, faults);
        jdbc.sql("UPDATE orders SET status = 'CONFIRMED', amount_cents = ? WHERE id = ?")
                .params(amountCents, orderId)
                .update();
    }

    @Override
    public void markFailed(long orderId) {
        SlowQuery.apply(jdbc, faults);
        jdbc.sql("UPDATE orders SET status = 'FAILED' WHERE id = ?").params(orderId).update();
    }
}
