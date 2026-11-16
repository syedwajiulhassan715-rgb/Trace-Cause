package dev.tracecause.inventory;

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
public class InventoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }

    @Bean
    StockStore stockStore(JdbcClient jdbc, FaultState faults) {
        return (sku, quantity) -> {
            SlowQuery.apply(jdbc, faults);
            return jdbc
                    .sql("UPDATE inventory SET reserved = reserved + ? WHERE sku = ? RETURNING unit_price_cents")
                    .params(quantity, sku)
                    .query(Long.class)
                    .optional();
        };
    }
}
