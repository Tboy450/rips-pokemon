import unittest

from rips_ai.core import cents_to_dollars
from rips_ai.screen import (
    Region,
    advice_from_observation,
    classify_screen_text,
    extract_money_cents,
    observation_from_text,
)


class ScreenParsingTests(unittest.TestCase):
    def test_extract_money(self):
        self.assertEqual(
            [cents_to_dollars(value) for value in extract_money_cents("$1 $2.50 13.05")],
            ["$1.00", "$2.50", "$13.05"],
        )

    def test_observation_from_labeled_text(self):
        observation = observation_from_text(
            """
            Balance $14.50
            Vault $3.00
            Sell Value $0.72
            """
        )

        self.assertEqual(observation.bank_cents, 1450)
        self.assertEqual(observation.vault_cents, 300)
        self.assertEqual(observation.card_value_cents, 72)
        self.assertEqual(advice_from_observation(observation), "sell: card $0.72 vs vault $3.00")

    def test_advice_vaults_better_card(self):
        observation = observation_from_text(
            """
            Cash $12.00
            Vault $3.00
            Card Value $5.25
            """
        )

        self.assertEqual(advice_from_observation(observation), "vault: card $5.25 vs vault $3.00")

    def test_region_dataclass(self):
        region = Region("bank", 1, 2, 3, 4)

        self.assertEqual(region.name, "bank")
        self.assertEqual(region.whitelist, "$0123456789.")

    def test_classify_screen_text(self):
        self.assertEqual(classify_screen_text("Accept Buyback Offer\nBuyback offer $2.50"), "buyback")
        self.assertEqual(classify_screen_text("Estimated Payout Odds\nApply"), "pack_style")
        self.assertEqual(classify_screen_text("$0.30\nSell Vault"), "result")
        self.assertEqual(classify_screen_text("Pokemon Starter Pack\nBuy for $1"), "pack")


if __name__ == "__main__":
    unittest.main()
