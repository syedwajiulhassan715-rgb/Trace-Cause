package dev.tracecause.payments;

import dev.tracecause.faults.FaultState;
import dev.tracecause.faults.FaultsConfiguration;
import dev.tracecause.faults.SlowQuery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;

@SpringBootApplication
@Import(FaultsConfiguration.class)
public class PaymentsApplication {

    public static void main(String[] args) {
        SpringApplication.run(PaymentsApplication.class, args);
    }

    @Bean
    PaymentStore paymentStore(JdbcClient jdbc, FaultState faults) {
        return (orderId, amountCents) -> {
            SlowQuery.apply(jdbc, faults);
            return jdbc
                    .sql("INSERT INTO payments (order_id, amount_cents, status) VALUES (?, ?, 'CAPTURED') RETURNING id")
                    .params(orderId, amountCents)
                    .query(Long.class)
                    .single();
        };
    }
}
