import tempfile
import unittest
from pathlib import Path

from rips_ai.session import (
    begin_pending_pack,
    commit_buyback,
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
        action = advise_pending_result(session, 30)
        event = commit_buyback(session, 30)

        self.assertEqual(action, "sell")
        self.assertEqual(session.bank_cents, 1330)
        self.assertEqual(session.vault_cents, 250)
        self.assertEqual(session.opened_count, 1)
        self.assertEqual(event["action"], "sell")

    def test_buy_then_vault_keeps_post_buy_bank(self):
        session = start_live_session(bank_cents=1400, vault_cents=250, min_bank_cents=1000)

        begin_pending_pack(session, "two_fifty", 250)
        action = advise_pending_result(session, 500)
        commit_vault(session)

        self.assertEqual(action, "vault")
        self.assertEqual(session.bank_cents, 1150)
        self.assertEqual(session.vault_cents, 500)
        self.assertEqual(session.opened_count, 1)

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


if __name__ == "__main__":
    unittest.main()
