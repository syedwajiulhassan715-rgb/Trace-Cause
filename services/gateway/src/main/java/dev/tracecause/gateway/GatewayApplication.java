package dev.tracecause.gateway;

import dev.tracecause.faults.FaultsConfiguration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.web.client.RestClient;

@SpringBootApplication
@Import(FaultsConfiguration.class)
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }

    @Bean
    OrdersClient ordersClient(RestClient.Builder builder, @Value("${orders.url}") String ordersUrl) {
        return new HttpOrdersClient(builder.baseUrl(ordersUrl).build());
    }
}
