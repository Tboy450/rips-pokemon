import random
import unittest

from rips_ai.core import (
    BestExpectedValueStrategy,
    CardResult,
    GameState,
    Outcome,
    PackOption,
    apply_round,
    choose_bankroll_tier_pack,
    project_pack_open,
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

    def test_project_one_dollar_pack_uses_weighted_probabilities(self):
        pack = PackOption(
            "one_dollar",
            "$1 pack",
            100,
            (
                Outcome(50, 1),
                Outcome(200, 3),
            ),
        )

        projection = project_pack_open(
            bank_cents=1300,
            vault_cents=710,
            min_bank_cents=1000,
            pack=pack,
        )

        self.assertTrue(projection.can_buy)
        self.assertEqual(projection.bank_after_buy_cents, 1200)
        self.assertAlmostEqual(projection.sell_probability, 0.25)
        self.assertAlmostEqual(projection.vault_probability, 0.75)
        self.assertAlmostEqual(projection.total_profit_probability, 0.75)
        self.assertAlmostEqual(projection.expected_card_value_cents, 162.5)
        self.assertAlmostEqual(projection.expected_bank_after_cents, 1212.5)
        self.assertAlmostEqual(projection.expected_total_delta_cents, 62.5)

    def test_bankroll_tier_switches_between_one_and_two_fifty(self):
        one = PackOption("one_dollar", "$1 pack", 100, (Outcome(50, 1),))
        two = PackOption("two_fifty", "$2.50 pack", 250, (Outcome(250, 1),))

        below_threshold = choose_bankroll_tier_pack(
            bank_cents=1300,
            min_bank_cents=1000,
            packs=[one, two],
            two_fifty_bank_cents=1500,
        )
        at_threshold = choose_bankroll_tier_pack(
            bank_cents=1500,
            min_bank_cents=1000,
            packs=[one, two],
            two_fifty_bank_cents=1500,
        )

        self.assertEqual(below_threshold, one)
        self.assertEqual(at_threshold, two)

    def test_two_fifty_projection_uses_its_own_weights(self):
        one = PackOption(
            "one_dollar",
            "$1 pack",
            100,
            (
                Outcome(50, 9),
                Outcome(200, 1),
            ),
        )
        two = PackOption(
            "two_fifty",
            "$2.50 pack",
            250,
            (
                Outcome(100, 1),
                Outcome(500, 3),
            ),
        )

        one_projection = project_pack_open(1500, 710, 1000, one)
        two_projection = project_pack_open(1500, 710, 1000, two)

        self.assertAlmostEqual(one_projection.vault_probability, 0.1)
        self.assertAlmostEqual(two_projection.vault_probability, 0.75)
        self.assertAlmostEqual(one_projection.expected_card_value_cents, 65)
        self.assertAlmostEqual(two_projection.expected_card_value_cents, 400)


if __name__ == "__main__":
    unittest.main()
