package dev.tracecause.gateway;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;

@SpringBootApplication
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }

    @Bean
    OrdersClient ordersClient(RestClient.Builder builder, @Value("${orders.url}") String ordersUrl) {
        return new HttpOrdersClient(builder.baseUrl(ordersUrl).build());
    }
}
