import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from rips_ai.cli import main
from rips_ai.ledger import load_ledger_records


class CliSessionLedgerTests(unittest.TestCase):
    def test_session_plan_reports_weighted_one_dollar_probability(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "packs.json"
            session = root / "session.json"
            config.write_text(
                json.dumps(
                    {
                        "packs": [
                            {
                                "id": "one_dollar",
                                "name": "$1 Pack",
                                "price_cents": 100,
                                "outcomes": [
                                    {"value_cents": 50, "weight": 1},
                                    {"value_cents": 200, "weight": 3},
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "session-start",
                            "--session",
                            str(session),
                            "--bank",
                            "13",
                            "--vault",
                            "7.10",
                            "--vault-count",
                            "3",
                            "--force",
                        ]
                    ),
                    0,
                )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    main(
                        [
                            "session-plan",
                            "--session",
                            str(session),
                            "--config",
                            str(config),
                            "--pack",
                            "one_dollar",
                        ]
                    ),
                    0,
                )

        text = output.getvalue()
        self.assertIn("pack: $1 Pack (one_dollar)", text)
        self.assertIn("sell probability: 25.0%", text)
        self.assertIn("vault probability: 75.0%", text)

    def test_committed_buyback_writes_session_event_to_ledger(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "packs.json"
            session = root / "session.json"
            ledger = root / "outcomes.jsonl"
            config.write_text(
                json.dumps(
                    {
                        "packs": [
                            {
                                "id": "one_dollar",
                                "name": "$1 Pack",
                                "price_cents": 100,
                                "outcomes": [{"value_cents": 50, "weight": 1}],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "session-start",
                            "--session",
                            str(session),
                            "--bank",
                            "14",
                            "--vault",
                            "3",
                            "--force",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(
                        [
                            "session-buy",
                            "--session",
                            str(session),
                            "--config",
                            str(config),
                            "--pack",
                            "one_dollar",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(
                        [
                            "session-result",
                            "--session",
                            str(session),
                            "--card-value",
                            "0.50",
                            "--rarity-hint",
                            "blue flashes",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(
                        [
                            "session-buyback",
                            "--session",
                            str(session),
                            "--amount",
                            "0.50",
                            "--commit",
                            "--ledger",
                            str(ledger),
                        ]
                    ),
                    0,
                )

            records = load_ledger_records(ledger)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["pack_id"], "one_dollar")
        self.assertEqual(records[0]["action"], "sell")
        self.assertEqual(records[0]["rarity_hint"], "blue flashes")
        self.assertEqual(records[0]["bank_before_cents"], 1400)
        self.assertEqual(records[0]["bank_after_cents"], 1350)

    def test_export_ledger_config_writes_observed_pack_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "packs.json"
            ledger = root / "outcomes.jsonl"
            output = root / "observed.json"
            config.write_text(
                json.dumps(
                    {
                        "packs": [
                            {
                                "id": "one_dollar",
                                "name": "$1 Pack",
                                "price_cents": 100,
                                "outcomes": [{"value_cents": 50, "weight": 1}],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            ledger.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "pack_id": "one_dollar",
                                "pack_price_cents": 100,
                                "card_value_cents": 50,
                                "action": "sell",
                            }
                        ),
                        json.dumps(
                            {
                                "pack_id": "one_dollar",
                                "pack_price_cents": 100,
                                "card_value_cents": 250,
                                "action": "vault",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()):
                result = main(
                    [
                        "export-ledger-config",
                        "--ledger",
                        str(ledger),
                        "--config",
                        str(config),
                        "--output",
                        str(output),
                    ]
                )

            observed = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertEqual(observed["packs"][0]["name"], "$1 Pack")
        self.assertEqual(observed["packs"][0]["observations"], 2)
        self.assertEqual(observed["packs"][0]["outcomes"][1]["value_cents"], 250)


if __name__ == "__main__":
    unittest.main()
