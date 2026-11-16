import unittest

from eval.scenarios import FAULTS_FOR, Segment, generate, total_seconds


class GenerateTest(unittest.TestCase):

    def test_same_seed_same_schedule(self):
        self.assertEqual(generate(seed=100, n=20), generate(seed=100, n=20))

    def test_different_seeds_differ(self):
        self.assertNotEqual(generate(seed=100, n=20), generate(seed=200, n=20))

    def test_fault_types_fit_the_service(self):
        for s in generate(seed=1, n=200):
            self.assertIn(s.fault, FAULTS_FOR[s.service])
        # the gateway has no database, so it never gets a slow query
        self.assertNotIn("slow_query", FAULTS_FOR["gateway"])

    def test_ranges(self):
        segs = generate(seed=2, n=300)
        for s in segs:
            if s.kind == "incident":
                self.assertTrue(40 <= s.duration_s <= 60, s)
            else:
                self.assertEqual(s.kind, "blip")
                self.assertTrue(4 <= s.duration_s <= 10, s)
            self.assertTrue(45 <= s.gap_s <= 60, s)
            if s.fault == "errors":
                self.assertTrue(0.02 <= s.magnitude <= 0.40, s)
            else:
                self.assertTrue(2 <= s.magnitude <= 200, s)
        kinds = [s.kind for s in segs]
        self.assertAlmostEqual(kinds.count("incident") / len(kinds), 0.7, delta=0.08)

    def test_every_service_and_fault_appears(self):
        segs = generate(seed=3, n=200)
        self.assertEqual({s.service for s in segs}, set(FAULTS_FOR))
        self.assertEqual({s.fault for s in segs}, {"delay", "slow_query", "errors"})

    def test_fault_kwargs_for_the_injector(self):
        self.assertEqual(Segment(0, "incident", "orders", "delay", 25, 50, 50).fault_kwargs(),
                         {"delay_ms": 25, "seed": 0})
        self.assertEqual(Segment(3, "blip", "payments", "errors", 0.1, 6, 50).fault_kwargs(),
                         {"error_rate": 0.1, "seed": 3})
        self.assertEqual(Segment(4, "incident", "inventory", "slow_query", 40, 50, 50).fault_kwargs(),
                         {"slow_query_ms": 40, "seed": 4})

    def test_total_seconds(self):
        segs = [Segment(0, "incident", "orders", "delay", 25, 50, 45), Segment(1, "blip", "orders", "delay", 25, 5, 55)]
        self.assertEqual(total_seconds(segs, warmup_s=70, tail_s=40), 70 + 45 + 50 + 55 + 5 + 40)


if __name__ == "__main__":
    unittest.main()
