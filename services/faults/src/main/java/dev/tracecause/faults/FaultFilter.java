package dev.tracecause.faults;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Applies the active delay and error rate to every business request.
 * It runs inside the server span the OTel agent creates, so the delay is
 * this service's own time, and an injected 500 marks this service's span as failed.
 * Nothing about the fault is written into the trace: the analyzer has to find it.
 */
public class FaultFilter extends OncePerRequestFilter {

    @FunctionalInterface
    public interface Sleeper {
        void sleep(long ms) throws InterruptedException;
    }

    private final FaultState state;
    private final Sleeper sleeper;

    public FaultFilter(FaultState state) {
        this(state, Thread::sleep);
    }

    FaultFilter(FaultState state, Sleeper sleeper) {
        this.state = state;
        this.sleeper = sleeper;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return request.getRequestURI().startsWith("/admin/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        long delay = state.current().delayMs();
        if (delay > 0) {
            try {
                sleeper.sleep(delay);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new ServletException(e);
            }
        }
        if (state.shouldFail()) {
            response.setStatus(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write("{\"error\":\"internal error\"}");
            return;
        }
        chain.doFilter(request, response);
    }
}
