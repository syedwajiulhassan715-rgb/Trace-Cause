package dev.tracecause.payments;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class ChargeControllerTest {

    @Test
    void recordsPaymentAndReturnsId() throws Exception {
        long[] seen = new long[2];
        PaymentStore store = (orderId, amountCents) -> {
            seen[0] = orderId;
            seen[1] = amountCents;
            return 42L;
        };
        MockMvc mvc = MockMvcBuilders.standaloneSetup(new ChargeController(store)).build();

        mvc.perform(post("/charge")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"orderId\":7,\"amountCents\":500}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paymentId").value(42))
                .andExpect(jsonPath("$.status").value("CAPTURED"));

        assertThat(seen).containsExactly(7L, 500L);
    }
}
