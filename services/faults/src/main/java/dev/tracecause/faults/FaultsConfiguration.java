package dev.tracecause.faults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Add {@code @Import(FaultsConfiguration.class)} to a service to make it fault-injectable. */
@Configuration(proxyBeanMethods = false)
public class FaultsConfiguration {

    @Bean
    FaultState faultState() {
        return new FaultState();
    }

    @Bean
    FaultFilter faultFilter(FaultState state) {
        return new FaultFilter(state);
    }

    @Bean
    FaultController faultController(FaultState state) {
        return new FaultController(state);
    }
}
