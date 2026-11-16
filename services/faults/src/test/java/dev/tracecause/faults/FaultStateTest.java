package dev.tracecause.faults;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

class FaultStateTest {

    private static List<Boolean> flips(FaultState state, int n) {
        List<Boolean> out = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            out.add(state.shouldFail());
        }
        return out;
    }

    @Test
    void startsWithNoFault() {
        FaultState state = new FaultState();
        assertThat(state.current()).isEqualTo(Fault.NONE);
        assertThat(flips(state, 100)).containsOnly(false);
    }

    @Test
    void errorRateOneAlwaysFails() {
        FaultState state = new FaultState();
        state.set(new Fault(0, 1.0, 0, 7));
        assertThat(flips(state, 100)).containsOnly(true);
    }

    @Test
    void sameSeedReplaysSameSequence() {
        FaultState a = new FaultState();
        FaultState b = new FaultState();
        a.set(new Fault(0, 0.3, 0, 42));
        b.set(new Fault(0, 0.3, 0, 42));
        assertThat(flips(a, 200)).isEqualTo(flips(b, 200));
    }

    @Test
    void failureFractionIsCloseToRate() {
        FaultState state = new FaultState();
        state.set(new Fault(0, 0.3, 0, 1));
        long failures = flips(state, 10_000).stream().filter(f -> f).count();
        assertThat(failures).isBetween(2_800L, 3_200L);
    }

    @Test
    void clearRemovesFault() {
        FaultState state = new FaultState();
        state.set(new Fault(100, 1.0, 50, 1));
        state.clear();
        assertThat(state.current()).isEqualTo(Fault.NONE);
        assertThat(state.shouldFail()).isFalse();
    }

    @Test
    void rejectsOutOfRangeValues() {
        assertThatThrownBy(() -> new Fault(-1, 0, 0, 0)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Fault(0, 1.5, 0, 0)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Fault(0, Double.NaN, 0, 0)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Fault(0, 0, 60_001, 0)).isInstanceOf(IllegalArgumentException.class);
    }
}
