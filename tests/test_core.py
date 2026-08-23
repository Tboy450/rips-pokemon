import random
import unittest

from rips_ai.core import (
    BestExpectedValueStrategy,
    CardResult,
    GameState,
    Outcome,
    PackOption,
    apply_round,
    run_session,
)


class CoreTests(unittest.TestCase):
    def test_sell_new_card_when_it_does_not_beat_vault(self):
        pack = PackOption("one_dollar", "$1 pack", 100, (Outcome(50, 1),))
        state = GameState(bank_cents=1500, vault_card=CardResult(300, "vault"))
        strategy = BestExpectedValueStrategy(min_bank_cents=1000, play_negative_ev=True)

        result = apply_round(state, pack, CardResult(50, "new"), strategy)

        self.assertEqual(result.action, "sell")
        self.assertEqual(state.bank_cents, 1450)
        self.assertEqual(state.vault_value_cents, 300)

    def test_vault_new_best_card_and_sell_old_vault(self):
        pack = PackOption("one_dollar", "$1 pack", 100, (Outcome(500, 1),))
        state = GameState(bank_cents=1500, vault_card=CardResult(300, "vault"))
        strategy = BestExpectedValueStrategy(min_bank_cents=1000, play_negative_ev=True)

        result = apply_round(state, pack, CardResult(500, "new"), strategy)

        self.assertEqual(result.action, "vault")
        self.assertEqual(state.bank_cents, 1700)
        self.assertEqual(state.vault_value_cents, 500)

    def test_bank_floor_blocks_buy(self):
        pack = PackOption("one_dollar", "$1 pack", 100, (Outcome(500, 1),))
        state = GameState(bank_cents=1050)
        strategy = BestExpectedValueStrategy(min_bank_cents=1000, play_negative_ev=True)

        with self.assertRaises(ValueError):
            apply_round(state, pack, CardResult(500, "new"), strategy)

    def test_session_stops_at_bank_floor(self):
        pack = PackOption("one_dollar", "$1 pack", 100, (Outcome(0, 1),))
        strategy = BestExpectedValueStrategy(min_bank_cents=1000, play_negative_ev=True)

        state = run_session([pack], strategy, 1200, 100, random.Random(1))

        self.assertEqual(state.opened_count, 2)
        self.assertEqual(state.bank_cents, 1000)


if __name__ == "__main__":
    unittest.main()
