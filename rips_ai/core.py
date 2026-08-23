from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable, Literal


Action = Literal["sell", "vault"]


def dollars_to_cents(value: str | int | float | Decimal) -> int:
    text = str(value).strip().replace("$", "")
    amount = Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(amount * 100)


def cents_to_dollars(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100}.{cents % 100:02d}"


@dataclass(frozen=True)
class CardResult:
    value_cents: int
    label: str = "unknown card"
    rarity_hint: str | None = None


@dataclass(frozen=True)
class Outcome:
    value_cents: int
    weight: float
    label: str = "unknown card"


@dataclass(frozen=True)
class PackOption:
    id: str
    name: str
    price_cents: int
    outcomes: tuple[Outcome, ...]

    @property
    def expected_value_cents(self) -> float:
        total_weight = sum(outcome.weight for outcome in self.outcomes)
        if total_weight <= 0:
            return 0.0
        return sum(
            outcome.value_cents * outcome.weight for outcome in self.outcomes
        ) / total_weight

    @property
    def expected_profit_cents(self) -> float:
        return self.expected_value_cents - self.price_cents

    def sample(self, rng: random.Random) -> CardResult:
        if not self.outcomes:
            raise ValueError(f"pack {self.id!r} has no outcomes to sample")
        outcome = rng.choices(
            self.outcomes,
            weights=[item.weight for item in self.outcomes],
            k=1,
        )[0]
        return CardResult(value_cents=outcome.value_cents, label=outcome.label)


@dataclass
class RoundResult:
    pack_id: str
    pack_price_cents: int
    card_value_cents: int
    action: Action
    bank_after_cents: int
    vault_after_cents: int
    total_after_cents: int


@dataclass(frozen=True)
class PackOutcomeProjection:
    card_value_cents: int
    weight: float
    probability: float
    action: Action
    bank_after_cents: int
    vault_after_cents: int
    total_after_cents: int
    can_open_same_pack_again: bool


@dataclass(frozen=True)
class PackOpenProjection:
    pack_id: str
    pack_name: str
    price_cents: int
    bank_before_cents: int
    vault_before_cents: int
    min_bank_cents: int
    can_buy: bool
    bank_after_buy_cents: int
    expected_card_value_cents: float
    expected_bank_after_cents: float
    expected_total_after_cents: float
    sell_probability: float
    vault_probability: float
    total_profit_probability: float
    bank_profit_probability: float
    can_open_same_pack_again_probability: float
    worst_bank_after_cents: int
    best_bank_after_cents: int
    outcomes: tuple[PackOutcomeProjection, ...]

    @property
    def expected_card_profit_cents(self) -> float:
        return self.expected_card_value_cents - self.price_cents

    @property
    def expected_bank_delta_cents(self) -> float:
        return self.expected_bank_after_cents - self.bank_before_cents

    @property
    def expected_total_delta_cents(self) -> float:
        return self.expected_total_after_cents - (
            self.bank_before_cents + self.vault_before_cents
        )


@dataclass
class GameState:
    bank_cents: int
    vault_card: CardResult | None = None
    opened_count: int = 0
    total_spent_cents: int = 0
    total_sold_cents: int = 0
    history: list[RoundResult] = field(default_factory=list)

    @property
    def vault_value_cents(self) -> int:
        return 0 if self.vault_card is None else self.vault_card.value_cents

    @property
    def total_value_cents(self) -> int:
        return self.bank_cents + self.vault_value_cents

    def can_buy(self, pack: PackOption, min_bank_cents: int) -> bool:
        return self.bank_cents - pack.price_cents >= min_bank_cents


class BestExpectedValueStrategy:
    def __init__(
        self,
        min_bank_cents: int,
        allowed_pack_ids: Iterable[str] | None = None,
        play_negative_ev: bool = False,
    ) -> None:
        self.min_bank_cents = min_bank_cents
        self.allowed_pack_ids = set(allowed_pack_ids or [])
        self.play_negative_ev = play_negative_ev

    def choose_pack(
        self,
        state: GameState,
        packs: Iterable[PackOption],
    ) -> PackOption | None:
        eligible: list[PackOption] = []
        for pack in packs:
            if self.allowed_pack_ids and pack.id not in self.allowed_pack_ids:
                continue
            if not state.can_buy(pack, self.min_bank_cents):
                continue
            if not self.play_negative_ev and pack.expected_profit_cents < 0:
                continue
            eligible.append(pack)

        if not eligible:
            return None

        return max(
            eligible,
            key=lambda pack: (pack.expected_profit_cents, -pack.price_cents),
        )

    def choose_card_action(self, state: GameState, card: CardResult) -> Action:
        if state.vault_card is None:
            return "vault"
        if card.value_cents > state.vault_card.value_cents:
            return "vault"
        return "sell"


def apply_round(
    state: GameState,
    pack: PackOption,
    card: CardResult,
    strategy: BestExpectedValueStrategy,
) -> RoundResult:
    if not state.can_buy(pack, strategy.min_bank_cents):
        raise ValueError(
            f"buying {pack.id} would take bank below "
            f"{cents_to_dollars(strategy.min_bank_cents)}"
        )

    state.bank_cents -= pack.price_cents
    state.total_spent_cents += pack.price_cents

    action = strategy.choose_card_action(state, card)
    if action == "vault":
        if state.vault_card is not None:
            state.bank_cents += state.vault_card.value_cents
            state.total_sold_cents += state.vault_card.value_cents
        state.vault_card = card
    else:
        state.bank_cents += card.value_cents
        state.total_sold_cents += card.value_cents

    state.opened_count += 1
    result = RoundResult(
        pack_id=pack.id,
        pack_price_cents=pack.price_cents,
        card_value_cents=card.value_cents,
        action=action,
        bank_after_cents=state.bank_cents,
        vault_after_cents=state.vault_value_cents,
        total_after_cents=state.total_value_cents,
    )
    state.history.append(result)
    return result


def run_session(
    packs: Iterable[PackOption],
    strategy: BestExpectedValueStrategy,
    starting_bank_cents: int,
    max_opens: int,
    rng: random.Random,
) -> GameState:
    pack_list = list(packs)
    state = GameState(bank_cents=starting_bank_cents)
    for _ in range(max_opens):
        pack = strategy.choose_pack(state, pack_list)
        if pack is None:
            break
        apply_round(state, pack, pack.sample(rng), strategy)
    return state


def load_packs(path: Path) -> list[PackOption]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    packs: list[PackOption] = []
    for item in raw.get("packs", []):
        outcomes = tuple(
            Outcome(
                value_cents=int(outcome["value_cents"]),
                weight=float(outcome["weight"]),
                label=str(outcome.get("label", "unknown card")),
            )
            for outcome in item.get("outcomes", [])
        )
        packs.append(
            PackOption(
                id=str(item["id"]),
                name=str(item["name"]),
                price_cents=int(item["price_cents"]),
                outcomes=outcomes,
            )
        )
    if not packs:
        raise ValueError(f"no packs found in {path}")
    return packs


def find_pack(packs: Iterable[PackOption], pack_id: str) -> PackOption:
    for pack in packs:
        if pack.id == pack_id:
            return pack
    raise ValueError(f"unknown pack id: {pack_id}")


def choose_bankroll_tier_pack(
    bank_cents: int,
    min_bank_cents: int,
    packs: Iterable[PackOption],
    two_fifty_bank_cents: int,
    one_dollar_pack_id: str = "one_dollar",
    two_fifty_pack_id: str = "two_fifty",
) -> PackOption | None:
    by_id = {pack.id: pack for pack in packs}
    two_fifty = by_id.get(two_fifty_pack_id)
    if (
        two_fifty is not None
        and bank_cents >= two_fifty_bank_cents
        and bank_cents - two_fifty.price_cents >= min_bank_cents
    ):
        return two_fifty

    one_dollar = by_id.get(one_dollar_pack_id)
    if one_dollar is not None and bank_cents - one_dollar.price_cents >= min_bank_cents:
        return one_dollar

    return None


def round_to_record(
    result: RoundResult,
    bank_before_cents: int,
    vault_before_cents: int,
    rarity_hint: str | None,
) -> dict[str, Any]:
    return {
        "pack_id": result.pack_id,
        "pack_price_cents": result.pack_price_cents,
        "card_value_cents": result.card_value_cents,
        "rarity_hint": rarity_hint,
        "action": result.action,
        "bank_before_cents": bank_before_cents,
        "vault_before_cents": vault_before_cents,
        "bank_after_cents": result.bank_after_cents,
        "vault_after_cents": result.vault_after_cents,
        "total_after_cents": result.total_after_cents,
    }


def decide_revealed_card(vault_value_cents: int, card_value_cents: int) -> Action:
    if card_value_cents > vault_value_cents:
        return "vault"
    return "sell"


def project_pack_open(
    bank_cents: int,
    vault_cents: int,
    min_bank_cents: int,
    pack: PackOption,
) -> PackOpenProjection:
    total_weight = sum(outcome.weight for outcome in pack.outcomes)
    if total_weight <= 0:
        raise ValueError(f"pack {pack.id!r} has no positive outcome weight")

    bank_after_buy = bank_cents - pack.price_cents
    can_buy = bank_after_buy >= min_bank_cents
    projected_outcomes: list[PackOutcomeProjection] = []

    for outcome in pack.outcomes:
        probability = outcome.weight / total_weight
        action: Action = "vault" if outcome.value_cents > pack.price_cents else "sell"
        if action == "vault":
            bank_after = bank_after_buy
            vault_after = vault_cents + outcome.value_cents
        else:
            bank_after = bank_after_buy + outcome.value_cents
            vault_after = vault_cents

        projected_outcomes.append(
            PackOutcomeProjection(
                card_value_cents=outcome.value_cents,
                weight=outcome.weight,
                probability=probability,
                action=action,
                bank_after_cents=bank_after,
                vault_after_cents=vault_after,
                total_after_cents=bank_after + vault_after,
                can_open_same_pack_again=bank_after - pack.price_cents >= min_bank_cents,
            )
        )

    expected_card = sum(
        projection.card_value_cents * projection.probability
        for projection in projected_outcomes
    )
    expected_bank_after = sum(
        projection.bank_after_cents * projection.probability
        for projection in projected_outcomes
    )
    expected_total_after = sum(
        projection.total_after_cents * projection.probability
        for projection in projected_outcomes
    )

    return PackOpenProjection(
        pack_id=pack.id,
        pack_name=pack.name,
        price_cents=pack.price_cents,
        bank_before_cents=bank_cents,
        vault_before_cents=vault_cents,
        min_bank_cents=min_bank_cents,
        can_buy=can_buy,
        bank_after_buy_cents=bank_after_buy,
        expected_card_value_cents=expected_card,
        expected_bank_after_cents=expected_bank_after,
        expected_total_after_cents=expected_total_after,
        sell_probability=sum(
            projection.probability
            for projection in projected_outcomes
            if projection.action == "sell"
        ),
        vault_probability=sum(
            projection.probability
            for projection in projected_outcomes
            if projection.action == "vault"
        ),
        total_profit_probability=sum(
            projection.probability
            for projection in projected_outcomes
            if projection.card_value_cents > pack.price_cents
        ),
        bank_profit_probability=sum(
            projection.probability
            for projection in projected_outcomes
            if projection.bank_after_cents > bank_cents
        ),
        can_open_same_pack_again_probability=sum(
            projection.probability
            for projection in projected_outcomes
            if projection.can_open_same_pack_again
        ),
        worst_bank_after_cents=min(
            projection.bank_after_cents for projection in projected_outcomes
        ),
        best_bank_after_cents=max(
            projection.bank_after_cents for projection in projected_outcomes
        ),
        outcomes=tuple(projected_outcomes),
    )
