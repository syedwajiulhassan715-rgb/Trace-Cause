package dev.tracecause.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.simple.JdbcClient;

@SpringBootApplication
public class InventoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }

    @Bean
    StockStore stockStore(JdbcClient jdbc) {
        return (sku, quantity) -> jdbc
                .sql("UPDATE inventory SET reserved = reserved + ? WHERE sku = ? RETURNING unit_price_cents")
                .params(quantity, sku)
                .query(Long.class)
                .optional();
    }
}
