import unittest

from core.taxonomy import get_dictionary, map_field


class TaxonomyRegressionTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = get_dictionary("aladdin")

    def test_core_fields_still_auto_map(self):
        expected_targets = {
            "portfolio_id": "portfolio_id",
            "trade_date": "trade_date",
            "settlement_date": "settlement_date",
            "maturity_date": "maturity_date",
            "market_value": "market_value",
        }

        for field_name, expected_target in expected_targets.items():
            with self.subTest(field_name=field_name):
                result = map_field(field_name, self.taxonomy)
                self.assertEqual(result["status"], "auto")
                self.assertEqual(result["target_field"], expected_target)

    def test_borderline_semantic_matches_route_to_review_or_auto(self):
        benchmark = map_field("benchmark_id", self.taxonomy)
        self.assertEqual(benchmark["status"], "review")
        self.assertEqual(benchmark["target_field"], "benchmark")

        broker = map_field("broker_code", self.taxonomy)
        self.assertEqual(broker["status"], "auto")
        self.assertEqual(broker["target_field"], "broker")

    def test_known_bad_matches_now_fail_closed(self):
        fields = [
            "custodian_name",
            "order_id",
            "position_date",
            "report_date",
            "trade_status",
        ]

        for field_name in fields:
            with self.subTest(field_name=field_name):
                result = map_field(field_name, self.taxonomy)
                self.assertEqual(result["status"], "no_match")
                self.assertIsNone(result["target_field"])


if __name__ == "__main__":
    unittest.main()
