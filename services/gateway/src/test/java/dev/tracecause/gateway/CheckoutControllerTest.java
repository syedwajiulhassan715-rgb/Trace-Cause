package dev.tracecause.gateway;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class CheckoutControllerTest {

    @Test
    void forwardsCheckoutToOrders() throws Exception {
        OrdersClient orders = req -> new OrderResponse(7, "CONFIRMED", req.quantity() * 250L);
        MockMvc mvc = MockMvcBuilders.standaloneSetup(new CheckoutController(orders)).build();

        mvc.perform(post("/checkout")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sku\":\"SKU-1\",\"quantity\":2}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value(7))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andExpect(jsonPath("$.amountCents").value(500));
    }

    @Test
    void returnsBadGatewayWhenOrdersFails() throws Exception {
        OrdersClient orders = req -> {
            throw new DownstreamException("orders", "boom");
        };
        MockMvc mvc = MockMvcBuilders.standaloneSetup(new CheckoutController(orders)).build();

        mvc.perform(post("/checkout")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sku\":\"SKU-1\",\"quantity\":1}"))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.failedService").value("orders"));
    }
}
