package dev.tracecause.inventory;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class ReserveControllerTest {

    private final StockStore store = (sku, qty) -> "SKU-1".equals(sku) ? Optional.of(250L) : Optional.empty();
    private final MockMvc mvc = MockMvcBuilders.standaloneSetup(new ReserveController(store)).build();

    @Test
    void returnsUnitPriceForKnownSku() throws Exception {
        mvc.perform(post("/reserve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sku\":\"SKU-1\",\"quantity\":2}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("SKU-1"))
                .andExpect(jsonPath("$.unitPriceCents").value(250));
    }

    @Test
    void returnsNotFoundForUnknownSku() throws Exception {
        mvc.perform(post("/reserve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sku\":\"NOPE\",\"quantity\":1}"))
                .andExpect(status().isNotFound());
    }
}
