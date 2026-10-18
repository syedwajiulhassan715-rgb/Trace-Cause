package dev.tracecause.payments;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.simple.JdbcClient;

@SpringBootApplication
public class PaymentsApplication {

    public static void main(String[] args) {
        SpringApplication.run(PaymentsApplication.class, args);
    }

    @Bean
    PaymentStore paymentStore(JdbcClient jdbc) {
        return (orderId, amountCents) -> jdbc
                .sql("INSERT INTO payments (order_id, amount_cents, status) VALUES (?, ?, 'CAPTURED') RETURNING id")
                .params(orderId, amountCents)
                .query(Long.class)
                .single();
    }
}
