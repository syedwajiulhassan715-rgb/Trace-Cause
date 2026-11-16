package dev.tracecause.faults;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

class FaultFilterTest {

    @RestController
    static class Business {
        @GetMapping("/work")
        String work() {
            return "done";
        }
    }

    private final FaultState state = new FaultState();
    private final List<Long> sleeps = new ArrayList<>();
    private final MockMvc mvc = MockMvcBuilders
            .standaloneSetup(new Business(), new FaultController(state))
            .addFilters(new FaultFilter(state, sleeps::add))
            .build();

    @Test
    void passesThroughWhenNoFault() throws Exception {
        mvc.perform(get("/work")).andExpect(status().isOk()).andExpect(content().string("done"));
        assertThat(sleeps).isEmpty();
    }

    @Test
    void sleepsForConfiguredDelay() throws Exception {
        state.set(new Fault(250, 0, 0, 0));
        mvc.perform(get("/work")).andExpect(status().isOk());
        assertThat(sleeps).containsExactly(250L);
    }

    @Test
    void returns500WhenErrorInjected() throws Exception {
        state.set(new Fault(0, 1.0, 0, 0));
        mvc.perform(get("/work")).andExpect(status().isInternalServerError());
    }

    @Test
    void adminEndpointIsNeverFaulted() throws Exception {
        state.set(new Fault(500, 1.0, 0, 0));
        mvc.perform(get("/admin/fault")).andExpect(status().isOk()).andExpect(jsonPath("$.delayMs").value(500));
        assertThat(sleeps).isEmpty();
    }

    @Test
    void putSetsAndDeleteClearsFault() throws Exception {
        mvc.perform(put("/admin/fault").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"delayMs\":120,\"errorRate\":0.25,\"slowQueryMs\":30,\"seed\":9}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.errorRate").value(0.25));
        assertThat(state.current()).isEqualTo(new Fault(120, 0.25, 30, 9));

        mvc.perform(delete("/admin/fault")).andExpect(status().isOk());
        assertThat(state.current()).isEqualTo(Fault.NONE);
    }

    @Test
    void missingFieldsDefaultToZero() throws Exception {
        mvc.perform(put("/admin/fault").contentType(MediaType.APPLICATION_JSON).content("{\"delayMs\":80}"))
                .andExpect(status().isOk());
        assertThat(state.current()).isEqualTo(new Fault(80, 0, 0, 0));
    }

    @Test
    void rejectsInvalidFault() throws Exception {
        mvc.perform(put("/admin/fault").contentType(MediaType.APPLICATION_JSON).content("{\"errorRate\":2}"))
                .andExpect(status().isBadRequest());
        assertThat(state.current()).isEqualTo(Fault.NONE);
    }
}
