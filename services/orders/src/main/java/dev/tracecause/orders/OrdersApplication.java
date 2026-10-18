package dev.tracecause.orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }

    record ReserveRequest(String sku, int quantity) {
    }

    record ReserveResponse(String sku, long unitPriceCents) {
    }

    record ChargeRequest(long orderId, long amountCents) {
    }

    @Bean
    InventoryClient inventoryClient(RestClient.Builder builder, @Value("${inventory.url}") String url) {
        RestClient http = builder.clone().baseUrl(url).build();
        return (sku, quantity) -> {
            try {
                return http.post().uri("/reserve").body(new ReserveRequest(sku, quantity))
                        .retrieve().body(ReserveResponse.class).unitPriceCents();
            } catch (RestClientException e) {
                throw new DownstreamException("inventory", e.getMessage());
            }
        };
    }

    @Bean
    PaymentsClient paymentsClient(RestClient.Builder builder, @Value("${payments.url}") String url) {
        RestClient http = builder.clone().baseUrl(url).build();
        return (orderId, amountCents) -> {
            try {
                http.post().uri("/charge").body(new ChargeRequest(orderId, amountCents))
                        .retrieve().toBodilessEntity();
            } catch (RestClientException e) {
                throw new DownstreamException("payments", e.getMessage());
            }
        };
    }
}
