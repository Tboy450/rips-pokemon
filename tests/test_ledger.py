import tempfile
import unittest
from pathlib import Path

from rips_ai.ledger import (
    append_ledger_record,
    build_observed_pack_config,
    load_ledger_records,
    summarize_records_by_pack,
)


class LedgerTests(unittest.TestCase):
    def test_append_ledger_record_adds_timestamp_and_round_trips(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data" / "outcomes.jsonl"
            append_ledger_record(
                path,
                {
                    "pack_id": "one_dollar",
                    "pack_price_cents": 100,
                    "card_value_cents": 72,
                    "action": "sell",
                },
                recorded_at="2026-08-23T00:00:00+00:00",
            )

            records = load_ledger_records(path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["recorded_at"], "2026-08-23T00:00:00+00:00")
        self.assertEqual(records[0]["card_value_cents"], 72)

    def test_summarize_records_by_pack(self):
        summaries = summarize_records_by_pack(
            [
                {
                    "pack_id": "one_dollar",
                    "pack_price_cents": 100,
                    "card_value_cents": 50,
                    "action": "sell",
                },
                {
                    "pack_id": "one_dollar",
                    "pack_price_cents": 100,
                    "card_value_cents": 250,
                    "action": "vault",
                },
                {
                    "pack_id": "two_fifty",
                    "pack_price_cents": 250,
                    "card_value_cents": 300,
                    "action": "sell",
                },
            ]
        )

        self.assertEqual([summary.pack_id for summary in summaries], ["one_dollar", "two_fifty"])
        self.assertEqual(summaries[0].observations, 2)
        self.assertEqual(summaries[0].average_card_value_cents, 150)
        self.assertEqual(summaries[0].average_observed_profit_cents, 50)
        self.assertEqual(summaries[0].sell_count, 1)
        self.assertEqual(summaries[0].vault_count, 1)

    def test_build_observed_pack_config_groups_duplicate_values(self):
        config = build_observed_pack_config(
            [
                {
                    "pack_id": "one_dollar",
                    "pack_price_cents": 100,
                    "card_value_cents": 50,
                    "action": "sell",
                },
                {
                    "pack_id": "one_dollar",
                    "pack_price_cents": 100,
                    "card_value_cents": 50,
                    "action": "sell",
                },
                {
                    "pack_id": "one_dollar",
                    "pack_price_cents": 100,
                    "card_value_cents": 250,
                    "action": "vault",
                },
            ],
            {"one_dollar": "$1 Pack"},
        )

        pack = config["packs"][0]

        self.assertEqual(pack["name"], "$1 Pack")
        self.assertEqual(pack["observations"], 3)
        self.assertEqual(
            pack["outcomes"],
            [
                {"value_cents": 50, "weight": 2, "label": "observed $0.50"},
                {"value_cents": 250, "weight": 1, "label": "observed $2.50"},
            ],
        )

    def test_build_observed_pack_config_rejects_inconsistent_prices(self):
        with self.assertRaises(ValueError):
            build_observed_pack_config(
                [
                    {
                        "pack_id": "one_dollar",
                        "pack_price_cents": 100,
                        "card_value_cents": 50,
                    },
                    {
                        "pack_id": "one_dollar",
                        "pack_price_cents": 250,
                        "card_value_cents": 50,
                    },
                ]
            )


if __name__ == "__main__":
    unittest.main()
