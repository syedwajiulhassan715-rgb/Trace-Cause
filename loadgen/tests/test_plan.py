import unittest

from loadgen.faults import SERVICES, fault_body, admin_url
from loadgen.load import SKUS, plan


class PlanTest(unittest.TestCase):

    def test_same_seed_gives_same_plan(self):
        self.assertEqual(plan(seed=7, rate=20, duration_s=30), plan(seed=7, rate=20, duration_s=30))

    def test_different_seed_gives_different_plan(self):
        self.assertNotEqual(plan(seed=1, rate=20, duration_s=30), plan(seed=2, rate=20, duration_s=30))

    def test_offsets_are_sorted_and_inside_duration(self):
        p = plan(seed=3, rate=50, duration_s=10)
        offsets = [r.offset_s for r in p]
        self.assertEqual(offsets, sorted(offsets))
        self.assertTrue(all(0 <= o < 10 for o in offsets))

    def test_average_rate_matches(self):
        # Poisson arrivals: 20 req/s over 600 s is 12000 expected; allow 3 %.
        n = len(plan(seed=11, rate=20, duration_s=600))
        self.assertAlmostEqual(n / 12000, 1.0, delta=0.03)

    def test_requests_use_known_skus_and_small_quantities(self):
        for r in plan(seed=5, rate=20, duration_s=20):
            self.assertIn(r.sku, SKUS)
            self.assertTrue(1 <= r.quantity <= 3)

    def test_rejects_non_positive_rate(self):
        with self.assertRaises(ValueError):
            plan(seed=0, rate=0, duration_s=10)


class FaultBodyTest(unittest.TestCase):

    def test_body_has_all_fields(self):
        self.assertEqual(fault_body(delay_ms=300, seed=4),
                         {"delayMs": 300, "errorRate": 0.0, "slowQueryMs": 0, "seed": 4})

    def test_rejects_bad_error_rate(self):
        with self.assertRaises(ValueError):
            fault_body(error_rate=1.5)

    def test_rejects_negative_delay(self):
        with self.assertRaises(ValueError):
            fault_body(delay_ms=-1)

    def test_admin_urls(self):
        self.assertEqual(admin_url("inventory"), "http://localhost:8082/admin/fault")
        self.assertEqual(set(SERVICES), {"gateway", "orders", "inventory", "payments"})
        with self.assertRaises(ValueError):
            admin_url("postgres")


if __name__ == "__main__":
    unittest.main()
