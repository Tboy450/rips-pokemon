import tempfile
import unittest
from pathlib import Path

from rips_ai.session import (
    begin_pending_pack,
    commit_buyback,
    commit_vault_audit,
    commit_state_reconciliation,
    commit_vault,
    load_live_session,
    save_live_session,
    start_live_session,
    advise_pending_result,
)


class LiveSessionTests(unittest.TestCase):
    def test_buy_then_sell_updates_bank_after_buyback(self):
        session = start_live_session(bank_cents=1400, vault_cents=250, min_bank_cents=1000)

        begin_pending_pack(session, "one_dollar", 100)
        action = advise_pending_result(session, 30, "blue flashes")
        advise_pending_result(session, 30)
        event = commit_buyback(session, 30)

        self.assertEqual(action, "sell")
        self.assertEqual(session.bank_cents, 1330)
        self.assertEqual(session.vault_cents, 250)
        self.assertEqual(session.opened_count, 1)
        self.assertEqual(event["action"], "sell")
        self.assertEqual(event["rarity_hint"], "blue flashes")

    def test_buy_then_vault_adds_to_vault_total(self):
        session = start_live_session(
            bank_cents=1400,
            vault_cents=710,
            min_bank_cents=1000,
            vault_count=3,
        )

        begin_pending_pack(session, "one_dollar", 100)
        action = advise_pending_result(session, 500)
        event = commit_vault(session)

        self.assertEqual(action, "vault")
        self.assertEqual(session.bank_cents, 1300)
        self.assertEqual(session.vault_cents, 1210)
        self.assertEqual(session.vault_count, 4)
        self.assertEqual(session.opened_count, 1)
        self.assertEqual(event["bank_return_cents"], 0)
        self.assertEqual(event["total_delta_cents"], 400)

    def test_bank_floor_blocks_pending_pack(self):
        session = start_live_session(bank_cents=1100, vault_cents=0, min_bank_cents=1000)

        with self.assertRaises(ValueError):
            begin_pending_pack(session, "two_fifty", 250)

    def test_save_and_load_pending_session(self):
        session = start_live_session(bank_cents=1400, vault_cents=250, min_bank_cents=1000)
        begin_pending_pack(session, "one_dollar", 100)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            save_live_session(path, session)
            loaded = load_live_session(path)

        self.assertEqual(loaded.bank_cents, 1300)
        self.assertIsNotNone(loaded.pending)
        self.assertEqual(loaded.pending.pack_id, "one_dollar")

    def test_buy_then_sell_keeps_vault_total(self):
        session = start_live_session(
            bank_cents=1300,
            vault_cents=710,
            min_bank_cents=1000,
            vault_count=3,
        )

        begin_pending_pack(session, "one_dollar", 100)
        action = advise_pending_result(session, 75)
        event = commit_buyback(session, 75)

        self.assertEqual(action, "sell")
        self.assertEqual(session.bank_cents, 1275)
        self.assertEqual(session.vault_cents, 710)
        self.assertEqual(session.vault_count, 3)
        self.assertEqual(event["bank_return_cents"], 75)
        self.assertEqual(event["total_delta_cents"], -25)

    def test_vault_audit_stores_individual_card_values(self):
        session = start_live_session(
            bank_cents=1650,
            vault_cents=680,
            min_bank_cents=1000,
            vault_count=2,
        )

        event = commit_vault_audit(
            session,
            observed_vault_cents=680,
            observed_vault_count=2,
            observed_vault_cards_cents=[670, 10],
        )

        self.assertEqual(session.vault_cards_cents, [670, 10])
        self.assertEqual(event["observed_vault_cards_cents"], [670, 10])

    def test_total_only_vault_audit_clears_stale_individual_card_values(self):
        session = start_live_session(
            bank_cents=1650,
            vault_cents=680,
            min_bank_cents=1000,
            vault_count=2,
            vault_cards_cents=[670, 10],
        )

        commit_vault_audit(
            session,
            observed_vault_cents=680,
            observed_vault_count=2,
        )

        self.assertEqual(session.vault_cards_cents, [])

    def test_total_only_state_reconcile_clears_stale_individual_card_values(self):
        session = start_live_session(
            bank_cents=1650,
            vault_cents=680,
            min_bank_cents=1000,
            vault_count=2,
            vault_cards_cents=[670, 10],
        )

        commit_state_reconciliation(
            session,
            observed_bank_cents=1650,
            observed_vault_cents=680,
            observed_vault_count=2,
        )

        self.assertEqual(session.vault_cards_cents, [])

    def test_known_vault_slots_replace_highest_card_when_new_card_beats_it(self):
        session = start_live_session(
            bank_cents=1650,
            vault_cents=340,
            min_bank_cents=1000,
            vault_count=2,
            vault_cards_cents=[330, 10],
        )

        begin_pending_pack(session, "one_dollar", 100)
        action = advise_pending_result(session, 350)
        event = commit_vault(session)

        self.assertEqual(action, "vault")
        self.assertEqual(session.bank_cents, 1880)
        self.assertEqual(session.vault_cents, 360)
        self.assertEqual(session.vault_count, 2)
        self.assertEqual(session.vault_cards_cents, [350, 10])
        self.assertEqual(event["replaced_vault_cents"], 330)
        self.assertEqual(event["bank_return_cents"], 330)
        self.assertEqual(event["total_delta_cents"], 250)

    def test_known_vault_slots_sell_when_new_card_does_not_beat_highest_card(self):
        session = start_live_session(
            bank_cents=1650,
            vault_cents=680,
            min_bank_cents=1000,
            vault_count=2,
            vault_cards_cents=[670, 10],
        )

        begin_pending_pack(session, "one_dollar", 100)
        action = advise_pending_result(session, 350)
        event = commit_buyback(session, 350)

        self.assertEqual(action, "sell")
        self.assertEqual(session.bank_cents, 1900)
        self.assertEqual(session.vault_cents, 680)
        self.assertEqual(session.vault_cards_cents, [670, 10])
        self.assertEqual(event["bank_return_cents"], 350)


if __name__ == "__main__":
    unittest.main()
