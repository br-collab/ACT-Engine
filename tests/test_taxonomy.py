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
        self.assertEqual(benchmark["status"], "auto")
        self.assertEqual(benchmark["target_field"], "benchmark_id")

        broker = map_field("broker_code", self.taxonomy)
        self.assertEqual(broker["status"], "auto")
        self.assertEqual(broker["target_field"], "broker")

    def test_missing_dictionary_entries_now_map_explicitly(self):
        expected_targets = {
            "custodian_name": "custodian",
            "corporate_action_id": "corporate_action_id",
            "corporate_action_type": "corporate_action",
            "order_id": "order_id",
            "trade_status": "trade_status",
            "position_date": "position_date",
            "report_date": "report_date",
            "nav": "nav",
            "abor_position": "abor_position",
            "ibor_position": "ibor_position",
            "recon_break_flag": "recon_break",
            "break_amount": "recon_break_amount",
            "break_reason": "recon_break_reason",
            "sector_code": "sector_code",
        }

        for field_name, expected_target in expected_targets.items():
            with self.subTest(field_name=field_name):
                result = map_field(field_name, self.taxonomy)
                self.assertEqual(result["target_field"], expected_target)
                self.assertIn(result["status"], {"auto", "review"})


if __name__ == "__main__":
    unittest.main()
