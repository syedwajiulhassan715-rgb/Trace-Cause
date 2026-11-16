package dev.tracecause.faults;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Admin endpoint used by the fault injector: GET shows, PUT sets, DELETE clears the fault. */
@RestController
@RequestMapping("/admin/fault")
public class FaultController {

    private final FaultState state;

    public FaultController(FaultState state) {
        this.state = state;
    }

    @GetMapping
    public Fault get() {
        return state.current();
    }

    /**
     * Request body for PUT. Fields are boxed because Jackson 3 (Spring Boot 4) rejects
     * missing primitives by default; a missing field means 0.
     */
    public record FaultRequest(Long delayMs, Double errorRate, Long slowQueryMs, Long seed) {

        Fault toFault() {
            return new Fault(orZero(delayMs), errorRate == null ? 0 : errorRate, orZero(slowQueryMs), orZero(seed));
        }

        private static long orZero(Long v) {
            return v == null ? 0 : v;
        }
    }

    @PutMapping
    public Fault set(@RequestBody FaultRequest request) {
        state.set(request.toFault());
        return state.current();
    }

    @DeleteMapping
    public Fault clear() {
        state.clear();
        return state.current();
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> invalid(IllegalArgumentException e) {
        return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
    }
}
