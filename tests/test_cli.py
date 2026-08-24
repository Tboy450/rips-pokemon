import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from rips_ai.cli import main
from rips_ai.ledger import load_ledger_records
from rips_ai.session import load_live_session


class CliSessionLedgerTests(unittest.TestCase):
    def write_pack_config(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "packs": [
                        {
                            "id": "one_dollar",
                            "name": "$1 Pack",
                            "price_cents": 100,
                            "outcomes": [
                                {"value_cents": 50, "weight": 9},
                                {"value_cents": 200, "weight": 1},
                            ],
                        },
                        {
                            "id": "two_fifty",
                            "name": "$2.50 Pack",
                            "price_cents": 250,
                            "outcomes": [
                                {"value_cents": 100, "weight": 1},
                                {"value_cents": 500, "weight": 3},
                            ],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

    def test_session_recommend_falls_back_to_one_dollar_below_two_fifty_threshold(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "packs.json"
            session = root / "session.json"
            self.write_pack_config(config)

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
                            "session-recommend",
                            "--session",
                            str(session),
                            "--config",
                            str(config),
                            "--two-fifty-bank",
                            "15",
                        ]
                    ),
                    0,
                )

        text = output.getvalue()
        self.assertIn("recommendation: open $1 Pack (one_dollar)", text)
        self.assertIn("tier: $1 fallback until bank reaches $15.00", text)

    def test_session_recommend_unlocks_two_fifty_at_threshold(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "packs.json"
            session = root / "session.json"
            self.write_pack_config(config)

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "session-start",
                            "--session",
                            str(session),
                            "--bank",
                            "15",
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
                            "session-recommend",
                            "--session",
                            str(session),
                            "--config",
                            str(config),
                            "--two-fifty-bank",
                            "15",
                        ]
                    ),
                    0,
                )

        text = output.getvalue()
        self.assertIn("recommendation: open $2.50 Pack (two_fifty)", text)
        self.assertIn("tier: $2.50 unlocked at $15.00", text)
        self.assertIn("vault probability: 75.0%", text)

    def test_session_buy_blocks_two_fifty_below_threshold(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "packs.json"
            session = root / "session.json"
            self.write_pack_config(config)

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
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = main(
                    [
                        "session-buy",
                        "--session",
                        str(session),
                        "--config",
                        str(config),
                        "--pack",
                        "two_fifty",
                        "--two-fifty-bank",
                        "15",
                    ]
                )

        self.assertEqual(result, 1)
        self.assertIn("$2.50 pack unlocks at $15.00 bank", stderr.getvalue())

    def test_session_buy_without_purchase_confirmation_does_not_mutate_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "packs.json"
            session = root / "session.json"
            self.write_pack_config(config)

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
                result = main(
                    [
                        "session-buy",
                        "--session",
                        str(session),
                        "--config",
                        str(config),
                        "--pack",
                        "one_dollar",
                    ]
                )

            loaded = load_live_session(session)

        self.assertEqual(result, 0)
        self.assertEqual(loaded.bank_cents, 1300)
        self.assertIsNone(loaded.pending)
        self.assertIn("--purchase-confirmed", output.getvalue())

    def test_session_screen_pack_commit_requires_purchase_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "packs.json"
            session = root / "session.json"
            self.write_pack_config(config)

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
                result = main(
                    [
                        "session-screen",
                        str(root / "pack.png"),
                        "--session",
                        str(session),
                        "--config",
                        str(config),
                        "--state",
                        "pack",
                        "--pack",
                        "one_dollar",
                        "--commit",
                    ]
                )

            loaded = load_live_session(session)

        self.assertEqual(result, 0)
        self.assertEqual(loaded.bank_cents, 1300)
        self.assertIsNone(loaded.pending)
        self.assertIn("--purchase-confirmed", output.getvalue())

    def test_session_screen_whats_inside_is_navigation_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session = root / "session.json"

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
                result = main(
                    [
                        "session-screen",
                        str(root / "screen.png"),
                        "--session",
                        str(session),
                        "--state",
                        "whats_inside",
                        "--commit",
                    ]
                )

            loaded = load_live_session(session)

        self.assertEqual(result, 0)
        self.assertEqual(loaded.bank_cents, 1300)
        self.assertIsNone(loaded.pending)
        text = output.getvalue()
        self.assertIn("screen: whats_inside", text)
        self.assertIn("action: go back", text)
        self.assertIn("committed: no session change", text)

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
                            "--purchase-confirmed",
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

    def test_session_bank_check_reports_mismatch_without_commit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = Path(temp_dir) / "session.json"

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "session-start",
                            "--session",
                            str(session),
                            "--bank",
                            "10",
                            "--vault",
                            "8.90",
                            "--vault-count",
                            "5",
                            "--force",
                        ]
                    ),
                    0,
                )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(
                    [
                        "session-bank-check",
                        "--session",
                        str(session),
                        "--bank",
                        "11",
                    ]
                )

            loaded = load_live_session(session)

        self.assertEqual(result, 0)
        self.assertEqual(loaded.bank_cents, 1000)
        text = output.getvalue()
        self.assertIn("tracked bank: $10.00", text)
        self.assertIn("observed bank: $11.00", text)
        self.assertIn("status: mismatch", text)

    def test_session_bank_check_commit_reconciles_bank(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = Path(temp_dir) / "session.json"

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "session-start",
                            "--session",
                            str(session),
                            "--bank",
                            "10",
                            "--vault",
                            "8.90",
                            "--vault-count",
                            "5",
                            "--force",
                        ]
                    ),
                    0,
                )
                result = main(
                    [
                        "session-bank-check",
                        "--session",
                        str(session),
                        "--bank",
                        "11",
                        "--source",
                        "visible app bank after draw",
                        "--commit",
                    ]
                )

            loaded = load_live_session(session)

        self.assertEqual(result, 0)
        self.assertEqual(loaded.bank_cents, 1100)
        self.assertEqual(loaded.history[-1]["type"], "bank_reconciliation")
        self.assertEqual(loaded.history[-1]["source"], "visible app bank after draw")

    def test_session_vault_audit_from_card_values_commit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = Path(temp_dir) / "session.json"

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "session-start",
                            "--session",
                            str(session),
                            "--bank",
                            "10",
                            "--vault",
                            "5",
                            "--vault-count",
                            "2",
                            "--force",
                        ]
                    ),
                    0,
                )
                result = main(
                    [
                        "session-vault-audit",
                        "--session",
                        str(session),
                        "--card-values",
                        "$1.00,$2.50",
                        "5.40",
                        "--commit",
                    ]
                )

            loaded = load_live_session(session)

        self.assertEqual(result, 0)
        self.assertEqual(loaded.vault_cents, 890)
        self.assertEqual(loaded.vault_count, 3)
        self.assertEqual(loaded.history[-1]["type"], "vault_audit")

    def test_session_reconcile_clears_stale_pending_when_committed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "packs.json"
            session = root / "session.json"
            self.write_pack_config(config)

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "session-start",
                            "--session",
                            str(session),
                            "--bank",
                            "11",
                            "--vault",
                            "8.90",
                            "--vault-count",
                            "5",
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
                            "--purchase-confirmed",
                        ]
                    ),
                    0,
                )

            dry_run = io.StringIO()
            with contextlib.redirect_stdout(dry_run):
                result = main(
                    [
                        "session-reconcile",
                        "--session",
                        str(session),
                        "--bank",
                        "11.30",
                        "--vault",
                        "8.90",
                        "--vault-count",
                        "5",
                        "--clear-pending",
                    ]
                )
            loaded = load_live_session(session)
            self.assertEqual(result, 0)
            self.assertEqual(loaded.bank_cents, 1000)
            self.assertIsNotNone(loaded.pending)
            self.assertIn("session mutation: none", dry_run.getvalue())

            with contextlib.redirect_stdout(io.StringIO()):
                result = main(
                    [
                        "session-reconcile",
                        "--session",
                        str(session),
                        "--bank",
                        "11.30",
                        "--vault",
                        "8.90",
                        "--vault-count",
                        "5",
                        "--clear-pending",
                        "--count-cleared-pending",
                        "--source",
                        "manual app state after notification",
                        "--commit",
                    ]
                )
            loaded = load_live_session(session)

        self.assertEqual(result, 0)
        self.assertEqual(loaded.bank_cents, 1130)
        self.assertEqual(loaded.vault_cents, 890)
        self.assertEqual(loaded.vault_count, 5)
        self.assertEqual(loaded.opened_count, 1)
        self.assertIsNone(loaded.pending)
        self.assertEqual(loaded.history[-1]["type"], "state_reconciliation")
        self.assertTrue(loaded.history[-1]["cleared_pending"])
        self.assertTrue(loaded.history[-1]["counted_cleared_pending"])

    def test_session_workflow_ready_includes_bank_and_vault_checks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "packs.json"
            session = root / "session.json"
            self.write_pack_config(config)

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
                            "8.90",
                            "--vault-count",
                            "5",
                            "--force",
                        ]
                    ),
                    0,
                )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(
                    [
                        "session-workflow",
                        "--session",
                        str(session),
                        "--config",
                        str(config),
                    ]
                )

        self.assertEqual(result, 0)
        text = output.getvalue()
        self.assertIn("stage: ready_for_bank_check_and_pack_choice", text)
        self.assertIn("session-bank-check --bank VALUE", text)
        self.assertIn("session-vault-audit --card-values VALUE", text)
        self.assertIn("device-open-pack --pack one_dollar --dry-run", text)
        self.assertIn("device-open-pack --pack one_dollar --confirmed-buy-screen", text)

    def test_session_workflow_pending_sell_includes_buyback_and_bank_check(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "packs.json"
            session = root / "session.json"
            self.write_pack_config(config)

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
                            "8.90",
                            "--vault-count",
                            "5",
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
                            "--purchase-confirmed",
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
                        ]
                    ),
                    0,
                )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(
                    [
                        "session-workflow",
                        "--session",
                        str(session),
                        "--config",
                        str(config),
                    ]
                )

        self.assertEqual(result, 0)
        text = output.getvalue()
        self.assertIn("stage: waiting_for_sell_buyback", text)
        self.assertIn("session-buyback --amount $0.50 --commit", text)
        self.assertIn("session-bank-check --bank VALUE", text)

    def test_device_open_pack_dry_run_does_not_mutate_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "packs.json"
            flow = root / "flow.json"
            session = root / "session.json"
            self.write_pack_config(config)
            flow.write_text(
                json.dumps(
                    {
                        "gestures": {
                            "tap_buy": {"at": [540, 1950]},
                            "spin_picker_left": {
                                "from": [820, 1220],
                                "to": [260, 1220],
                                "duration_ms": 600,
                            },
                            "spin_picker_right": {
                                "from": [260, 1220],
                                "to": [820, 1220],
                                "duration_ms": 600,
                            },
                            "tap_center_pack": {"at": [540, 1220]},
                            "slice_left_to_right": {
                                "from": [60, 1240],
                                "to": [1020, 1240],
                                "duration_ms": 700,
                            },
                            "speed_up_reveal_swipe": {
                                "from": [60, 1320],
                                "to": [1020, 1320],
                                "duration_ms": 250,
                                "delay_ms": 350,
                            },
                        }
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
                            "8.90",
                            "--vault-count",
                            "5",
                            "--force",
                        ]
                    ),
                    0,
                )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(
                    [
                        "device-open-pack",
                        "--session",
                        str(session),
                        "--config",
                        str(config),
                        "--flow",
                        str(flow),
                        "--pack",
                        "one_dollar",
                        "--dry-run",
                    ]
                )

            loaded = load_live_session(session)

        self.assertEqual(result, 0)
        self.assertEqual(loaded.bank_cents, 1300)
        self.assertIsNone(loaded.pending)
        text = output.getvalue()
        self.assertIn("dry-run: device-open-pack", text)
        self.assertIn("session mutation: none during dry run", text)
        self.assertIn("execution still requires --confirmed-buy-screen", text)
        self.assertIn("input tap 540 1950", text)

    def test_device_vault_gallery_plan_prints_card_points(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            flow = Path(temp_dir) / "flow.json"
            flow.write_text(
                json.dumps(
                    {
                        "vault_gallery": {
                            "columns": 2,
                            "rows": 2,
                            "pages": 1,
                            "first_card_center": [100, 200],
                            "x_step": 50,
                            "y_step": 60,
                            "long_press_ms": 900,
                            "between_cards_ms": 500,
                        },
                        "gestures": {},
                    }
                ),
                encoding="utf-8",
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(
                    [
                        "device-vault-gallery-plan",
                        "--flow",
                        str(flow),
                    ]
                )

        self.assertEqual(result, 0)
        text = output.getvalue()
        self.assertIn("gallery slots: 4", text)
        self.assertIn("card 4: page 1, row 2, column 2, center (150, 260)", text)


if __name__ == "__main__":
    unittest.main()
