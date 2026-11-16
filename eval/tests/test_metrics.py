import unittest

from eval.metrics import alarm_episodes, evaluate_set


def seg(kind, service, start, end):
    return {"kind": kind, "service": service, "start_s": start, "end_s": end}


# Clean time 0-1000 s. Three incidents, one blip.
SEGMENTS = [
    seg("incident", "orders", 100, 150),     # detected at window 110 and 120
    seg("incident", "payments", 300, 350),   # detected at window 330
    seg("incident", "gateway", 500, 550),    # missed
    seg("blip", "inventory", 700, 706),      # alerted at 700: a false alarm
]
ALERTS = [
    ("orders", 110), ("gateway", 110), ("orders", 120),
    ("payments", 330),
    ("inventory", 700),
    ("orders", 850), ("orders", 860),  # clean time: one episode
    ("orders", 950),                   # clean time: another episode
]
RANKINGS = {  # incident windows -> ranked services
    (110, 120): ["orders", "gateway", "inventory", "payments"],
    (330,): ["orders", "inventory", "payments", "gateway"],
}


def ranker(windows):
    return RANKINGS[tuple(sorted(windows))]


class MetricsTest(unittest.TestCase):

    def setUp(self):
        self.r = evaluate_set(SEGMENTS, ALERTS, ranker, clean_start_s=0, clean_end_s=1000, lag_s=20)

    def test_detection(self):
        self.assertEqual((self.r.incidents, self.r.detected), (3, 2))
        self.assertAlmostEqual(self.r.recall, 2 / 3)

    def test_delay_is_from_fault_start_to_end_of_first_alert_window(self):
        # orders: window 110-120 -> 20 s; payments: window 330-340 -> 40 s
        self.assertEqual(self.r.delays_s, [20, 40])
        self.assertEqual(self.r.median_delay_s, 30)

    def test_false_alarms(self):
        self.assertEqual((self.r.blips, self.r.blip_alarms), (1, 1))
        self.assertEqual(self.r.clean_episodes, 2)
        # TP 2, FP 1 blip + 2 clean episodes
        self.assertAlmostEqual(self.r.precision, 2 / 5)
        self.assertAlmostEqual(self.r.f1, 2 * (2 / 5) * (2 / 3) / (2 / 5 + 2 / 3))

    def test_clean_time_excludes_fault_and_lag(self):
        # 1000 s minus 4 segments with their 20 s lag: (70 + 70 + 70 + 26) = 236 s
        self.assertAlmostEqual(self.r.clean_hours, (1000 - 236) / 3600)

    def test_root_cause_accuracy_counts_missed_incidents_as_wrong(self):
        # orders ranked 1st (top-1 hit); payments ranked 3rd (top-3 hit); gateway missed
        self.assertAlmostEqual(self.r.top1, 1 / 3)
        self.assertAlmostEqual(self.r.top3, 2 / 3)
        self.assertAlmostEqual(self.r.top1_detected, 1 / 2)
        self.assertAlmostEqual(self.r.top3_detected, 2 / 2)

    def test_alarm_episodes_merge_adjacent_windows(self):
        self.assertEqual(alarm_episodes([850, 860, 950, 970, 980]), 3)
        self.assertEqual(alarm_episodes([]), 0)

    def test_no_alerts_at_all(self):
        r = evaluate_set(SEGMENTS, [], ranker, clean_start_s=0, clean_end_s=1000, lag_s=20)
        self.assertEqual((r.detected, r.precision, r.f1, r.top1, r.median_delay_s), (0, 0.0, 0.0, 0.0, None))


if __name__ == "__main__":
    unittest.main()
