from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from .core import (
    BestExpectedValueStrategy,
    CardResult,
    GameState,
    apply_round,
    cents_to_dollars,
    choose_bankroll_tier_pack,
    dollars_to_cents,
    find_pack,
    load_packs,
    project_pack_open,
    round_to_record,
    run_session,
)
from .device import DeviceAccessError, capture_screenshot
from .ledger import (
    append_ledger_record,
    build_observed_pack_config,
    load_ledger_records,
    summarize_records_by_pack,
)
from .screen import (
    advice_from_observation,
    classify_image,
    load_regions,
    observation_from_regions,
    observation_from_text,
    ocr_image,
)
from .session import (
    LiveSession,
    advise_pending_result,
    begin_pending_pack,
    commit_buyback,
    commit_vault,
    load_live_session,
    save_live_session,
    start_live_session,
)


DEFAULT_CONFIG = Path("config/packs.example.json")
DEFAULT_SESSION = Path("data/live_session.json")
DEFAULT_LEDGER = Path("data/outcomes.jsonl")
DEFAULT_TWO_FIFTY_BANK = "15.00"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m rips_ai",
        description="Simulate and track Rips by Triumph pack cycling decisions.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    simulate = subparsers.add_parser("simulate", help="run many simulated sessions")
    simulate.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    simulate.add_argument("--bank", default="25.00", help="starting cash bank")
    simulate.add_argument("--min-bank", default="10.00", help="cash floor")
    simulate.add_argument("--runs", type=int, default=1000)
    simulate.add_argument("--max-opens", type=int, default=100)
    simulate.add_argument("--seed", type=int, default=7)
    simulate.add_argument(
        "--allow-negative-ev",
        action="store_true",
        help="keep opening the best eligible pack even when observed EV is negative",
    )

    recommend = subparsers.add_parser("recommend", help="recommend the next action")
    recommend.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    recommend.add_argument("--bank", required=True, help="current cash bank")
    recommend.add_argument("--vault", default="0.00", help="current vault value")
    recommend.add_argument("--min-bank", default="10.00", help="cash floor")
    recommend.add_argument(
        "--allow-negative-ev",
        action="store_true",
        help="allow a pack recommendation even when observed EV is negative",
    )
    recommend.add_argument(
        "--card-value",
        help="optional revealed card value; reports sell/vault decision",
    )

    record = subparsers.add_parser("record", help="append one manual pack result")
    record.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    record.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    record.add_argument("--pack", required=True, help="pack id from config")
    record.add_argument("--bank", required=True, help="cash before buying the pack")
    record.add_argument("--vault", default="0.00", help="vault value before the pack")
    record.add_argument("--min-bank", default="10.00", help="cash floor")
    record.add_argument("--card-value", required=True, help="revealed card sell value")
    record.add_argument("--rarity-hint", help="visible color flash/pattern notes")

    analyze = subparsers.add_parser("analyze-ledger", help="summarize logged results")
    analyze.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)

    export_config = subparsers.add_parser(
        "export-ledger-config",
        help="write a pack config from observed ledger results",
    )
    export_config.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    export_config.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    export_config.add_argument("--output", type=Path, default=Path("data/packs.observed.json"))

    advise_text = subparsers.add_parser(
        "advise-text",
        help="parse OCR/UI text and recommend sell/vault from measured values",
    )
    advise_text.add_argument("--text", help="raw OCR or UI dump text")
    advise_text.add_argument("--text-file", type=Path, help="file containing OCR/UI text")

    read_screen = subparsers.add_parser(
        "read-screen",
        help="OCR a screenshot and recommend sell/vault from measured values",
    )
    read_screen.add_argument("image", type=Path)

    read_regions = subparsers.add_parser(
        "read-regions",
        help="crop calibrated screenshot regions before OCR",
    )
    read_regions.add_argument("image", type=Path)
    read_regions.add_argument(
        "--regions",
        type=Path,
        default=Path("config/screen_regions.example.json"),
    )
    read_regions.add_argument(
        "--state",
        choices=("pack", "result", "buyback", "all"),
        default="result",
        help="only OCR the fields expected for this screen state",
    )
    read_regions.add_argument("--vault", help="known/current vault value")
    read_regions.add_argument("--bank", help="known/current bank value override")

    advise_screen = subparsers.add_parser(
        "advise-screen",
        help="give state-specific Android screen advice from calibrated OCR regions",
    )
    advise_screen.add_argument("image", type=Path)
    advise_screen.add_argument(
        "--regions",
        type=Path,
        default=Path("config/screen_regions.example.json"),
    )
    advise_screen.add_argument(
        "--state",
        choices=("pack", "result", "buyback"),
        required=True,
    )
    advise_screen.add_argument("--pack-price", help="pack price for pack-state floor check")
    advise_screen.add_argument("--bank", help="known/current bank value override")
    advise_screen.add_argument("--vault", help="known/current vault value")
    advise_screen.add_argument("--min-bank", default="10.00")
    advise_screen.add_argument("--expected-sell", help="expected buyback amount")

    classify_screen = subparsers.add_parser(
        "classify-screen",
        help="OCR a screenshot and classify the Rips screen state",
    )
    classify_screen.add_argument("image", type=Path)

    session_start = subparsers.add_parser("session-start", help="start/reset live app tracking")
    session_start.add_argument("--session", type=Path, default=DEFAULT_SESSION)
    session_start.add_argument("--bank", required=True, help="current cash bank")
    session_start.add_argument("--vault", default="0.00", help="current vault total value")
    session_start.add_argument("--vault-count", type=int, default=0, help="number of cards currently in vault")
    session_start.add_argument("--min-bank", default="10.00", help="cash floor")
    session_start.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing session file",
    )

    session_status = subparsers.add_parser("session-status", help="show live tracking state")
    session_status.add_argument("--session", type=Path, default=DEFAULT_SESSION)

    session_recommend = subparsers.add_parser(
        "session-recommend",
        help="recommend the next pack from the tracked bank",
    )
    session_recommend.add_argument("--session", type=Path, default=DEFAULT_SESSION)
    session_recommend.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    session_recommend.add_argument(
        "--two-fifty-bank",
        default=DEFAULT_TWO_FIFTY_BANK,
        help="bank threshold that unlocks $2.50 packs",
    )
    session_recommend.add_argument(
        "--allow-negative-ev",
        action="store_true",
        help="allow best eligible pack even when observed EV is negative",
    )

    session_plan = subparsers.add_parser(
        "session-plan",
        help="show probability-adjusted bank/vault projection for a pack",
    )
    session_plan.add_argument("--session", type=Path, default=DEFAULT_SESSION)
    session_plan.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    session_plan.add_argument("--pack", default="one_dollar", help="pack id from config")
    session_plan.add_argument(
        "--two-fifty-bank",
        default=DEFAULT_TWO_FIFTY_BANK,
        help="bank threshold that unlocks $2.50 packs",
    )

    session_buy = subparsers.add_parser(
        "session-buy",
        help="mark a pack as bought/opening and deduct its price from tracked bank",
    )
    session_buy.add_argument("--session", type=Path, default=DEFAULT_SESSION)
    session_buy.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    session_buy.add_argument("--pack", required=True, help="pack id from config")
    session_buy.add_argument(
        "--two-fifty-bank",
        default=DEFAULT_TWO_FIFTY_BANK,
        help="bank threshold that unlocks $2.50 packs",
    )

    session_result = subparsers.add_parser(
        "session-result",
        help="read or enter the revealed card value and advise sell/vault",
    )
    session_result.add_argument("--session", type=Path, default=DEFAULT_SESSION)
    session_result.add_argument("--regions", type=Path, default=Path("config/screen_regions.example.json"))
    session_result.add_argument("--image", type=Path, help="result screen screenshot")
    session_result.add_argument("--card-value", help="manual revealed card value")
    session_result.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    session_result.add_argument("--rarity-hint", help="visible color flash/pattern notes")
    session_result.add_argument(
        "--commit-vault",
        action="store_true",
        help="if the advice is vault, immediately commit the vault result",
    )

    session_buyback = subparsers.add_parser(
        "session-buyback",
        help="verify a sell buyback amount and optionally commit it",
    )
    session_buyback.add_argument("--session", type=Path, default=DEFAULT_SESSION)
    session_buyback.add_argument("--regions", type=Path, default=Path("config/screen_regions.example.json"))
    session_buyback.add_argument("--image", type=Path, help="buyback sheet screenshot")
    session_buyback.add_argument("--amount", help="manual buyback amount")
    session_buyback.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    session_buyback.add_argument(
        "--commit",
        action="store_true",
        help="update tracked bank after accepting the buyback",
    )

    session_vault = subparsers.add_parser(
        "session-vault",
        help="commit a pending vault advice after tapping Vault in the app",
    )
    session_vault.add_argument("--session", type=Path, default=DEFAULT_SESSION)
    session_vault.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)

    session_screen = subparsers.add_parser(
        "session-screen",
        help="apply live session rules to one screenshot",
    )
    session_screen.add_argument("image", type=Path)
    session_screen.add_argument("--session", type=Path, default=DEFAULT_SESSION)
    session_screen.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    session_screen.add_argument("--regions", type=Path, default=Path("config/screen_regions.example.json"))
    session_screen.add_argument(
        "--state",
        choices=("auto", "pack", "result", "buyback"),
        default="auto",
    )
    session_screen.add_argument("--pack", help="pack id to mark bought on a pack screen")
    session_screen.add_argument(
        "--two-fifty-bank",
        default=DEFAULT_TWO_FIFTY_BANK,
        help="bank threshold that unlocks $2.50 packs",
    )
    session_screen.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    session_screen.add_argument("--rarity-hint", help="visible color flash/pattern notes")
    session_screen.add_argument(
        "--commit",
        action="store_true",
        help="commit the advised app action after you have performed it",
    )

    device_capture = subparsers.add_parser(
        "device-capture",
        help="capture the current Android screen through Shizuku",
    )
    device_capture.add_argument("--output", type=Path, default=Path("data/latest_screen.png"))
    device_capture.add_argument("--remote-path", default="/sdcard/rips_ai_latest_screen.png")

    device_advise = subparsers.add_parser(
        "device-advise",
        help="capture the current Android screen and run calibrated screen advice",
    )
    device_advise.add_argument("--output", type=Path, default=Path("data/latest_screen.png"))
    device_advise.add_argument("--remote-path", default="/sdcard/rips_ai_latest_screen.png")
    device_advise.add_argument("--regions", type=Path, default=Path("config/screen_regions.example.json"))
    device_advise.add_argument(
        "--state",
        choices=("pack", "result", "buyback"),
        required=True,
    )
    device_advise.add_argument("--pack-price", help="pack price for pack-state floor check")
    device_advise.add_argument("--bank", help="known/current bank value override")
    device_advise.add_argument("--vault", help="known/current vault value")
    device_advise.add_argument("--min-bank", default="10.00")
    device_advise.add_argument("--expected-sell", help="expected buyback amount")

    return parser


def command_simulate(args: argparse.Namespace) -> int:
    packs = load_packs(args.config)
    starting_bank = dollars_to_cents(args.bank)
    min_bank = dollars_to_cents(args.min_bank)
    rng = random.Random(args.seed)
    strategy = BestExpectedValueStrategy(
        min_bank_cents=min_bank,
        allowed_pack_ids={"one_dollar", "two_fifty"},
        play_negative_ev=args.allow_negative_ev,
    )

    sessions = [
        run_session(packs, strategy, starting_bank, args.max_opens, rng)
        for _ in range(args.runs)
    ]
    totals = [session.total_value_cents for session in sessions]
    banks = [session.bank_cents for session in sessions]
    vaults = [session.vault_value_cents for session in sessions]
    opens = [session.opened_count for session in sessions]
    profitable = sum(1 for total in totals if total > starting_bank)

    print(f"runs: {args.runs}")
    print(f"starting bank: {cents_to_dollars(starting_bank)}")
    print(f"cash floor: {cents_to_dollars(min_bank)}")
    print(f"avg opens: {statistics.mean(opens):.1f}")
    print(f"avg final cash: {cents_to_dollars(round(statistics.mean(banks)))}")
    print(f"avg vault card: {cents_to_dollars(round(statistics.mean(vaults)))}")
    print(f"avg total value: {cents_to_dollars(round(statistics.mean(totals)))}")
    print(f"median total value: {cents_to_dollars(round(statistics.median(totals)))}")
    print(f"profitable sessions: {profitable / args.runs:.1%}")
    return 0


def command_recommend(args: argparse.Namespace) -> int:
    packs = load_packs(args.config)
    state = GameState(
        bank_cents=dollars_to_cents(args.bank),
        vault_card=CardResult(dollars_to_cents(args.vault), "current vault")
        if dollars_to_cents(args.vault) > 0
        else None,
    )
    strategy = BestExpectedValueStrategy(
        min_bank_cents=dollars_to_cents(args.min_bank),
        allowed_pack_ids={"one_dollar", "two_fifty"},
        play_negative_ev=args.allow_negative_ev,
    )
    pack = strategy.choose_pack(state, packs)
    if pack is None:
        print("recommendation: stop")
        print("reason: no eligible pack keeps the bank floor and EV rules intact")
    else:
        print(f"recommendation: open {pack.name} ({pack.id})")
        print(f"price: {cents_to_dollars(pack.price_cents)}")
        print(f"estimated EV: {cents_to_dollars(round(pack.expected_value_cents))}")
        print(f"estimated profit: {cents_to_dollars(round(pack.expected_profit_cents))}")

    if args.card_value is not None:
        card = CardResult(dollars_to_cents(args.card_value), "revealed card")
        action = strategy.choose_card_action(state, card)
        print(f"card decision: {action}")
    return 0


def command_record(args: argparse.Namespace) -> int:
    packs = load_packs(args.config)
    pack = find_pack(packs, args.pack)
    bank_before = dollars_to_cents(args.bank)
    vault_before = dollars_to_cents(args.vault)
    state = GameState(
        bank_cents=bank_before,
        vault_card=CardResult(vault_before, "current vault")
        if vault_before > 0
        else None,
    )
    strategy = BestExpectedValueStrategy(min_bank_cents=dollars_to_cents(args.min_bank))
    card = CardResult(
        value_cents=dollars_to_cents(args.card_value),
        label="manual result",
        rarity_hint=args.rarity_hint,
    )
    result = apply_round(state, pack, card, strategy)
    record = round_to_record(result, bank_before, vault_before, args.rarity_hint)
    append_ledger_record(
        args.ledger,
        record,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )

    print(f"action: {result.action}")
    print(f"bank after: {cents_to_dollars(result.bank_after_cents)}")
    print(f"vault after: {cents_to_dollars(result.vault_after_cents)}")
    print(f"total after: {cents_to_dollars(result.total_after_cents)}")
    print(f"logged: {args.ledger}")
    return 0


def command_analyze_ledger(args: argparse.Namespace) -> int:
    if not args.ledger.exists():
        print(f"ledger not found: {args.ledger}", file=sys.stderr)
        return 1

    records = load_ledger_records(args.ledger)
    if not records:
        print(f"ledger is empty: {args.ledger}")
        return 0

    for summary in summarize_records_by_pack(records):
        print(summary.pack_id)
        print(f"  observations: {summary.observations}")
        print(f"  avg card value: {cents_to_dollars(summary.average_card_value_cents)}")
        print(f"  median card value: {cents_to_dollars(summary.median_card_value_cents)}")
        print(f"  best card: {cents_to_dollars(summary.best_card_value_cents)}")
        print(f"  avg observed profit: {cents_to_dollars(summary.average_observed_profit_cents)}")
        print(f"  actions: {summary.sell_count} sell, {summary.vault_count} vault")
    return 0


def command_export_ledger_config(args: argparse.Namespace) -> int:
    if not args.ledger.exists():
        print(f"ledger not found: {args.ledger}", file=sys.stderr)
        return 1

    records = load_ledger_records(args.ledger)
    if not records:
        print(f"ledger is empty: {args.ledger}", file=sys.stderr)
        return 1

    try:
        pack_names = {pack.id: pack.name for pack in load_packs(args.config)}
        config = build_observed_pack_config(records, pack_names)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"config: {args.output}")
    print(f"packs: {len(config['packs'])}")
    return 0


def _print_observation(text: str) -> int:
    observation = observation_from_text(text)
    print(f"bank: {cents_to_dollars(observation.bank_cents) if observation.bank_cents is not None else 'unknown'}")
    print(f"vault: {cents_to_dollars(observation.vault_cents) if observation.vault_cents is not None else 'unknown'}")
    print(
        "card value: "
        f"{cents_to_dollars(observation.card_value_cents) if observation.card_value_cents is not None else 'unknown'}"
    )
    print(f"advice: {advice_from_observation(observation)}")
    return 0


def command_advise_text(args: argparse.Namespace) -> int:
    if bool(args.text) == bool(args.text_file):
        print("provide exactly one of --text or --text-file", file=sys.stderr)
        return 2
    text = args.text if args.text is not None else args.text_file.read_text(encoding="utf-8")
    return _print_observation(text)


def command_read_screen(args: argparse.Namespace) -> int:
    text = ocr_image(args.image)
    print("ocr text:")
    print(text.strip())
    print()
    return _print_observation(text)


def command_read_regions(args: argparse.Namespace) -> int:
    regions = load_regions(args.regions)
    field_sets = {
        "pack": {"bank", "buy_button"},
        "result": {"revealed_card_value"},
        "buyback": {"buyback_offer"},
        "all": set(regions),
    }
    selected = {
        name: region
        for name, region in regions.items()
        if name in field_sets[args.state]
    }
    observation = observation_from_regions(args.image, selected)
    if args.vault is not None:
        observation = observation.__class__(
            bank_cents=observation.bank_cents,
            vault_cents=dollars_to_cents(args.vault),
            card_value_cents=observation.card_value_cents,
            raw_text=observation.raw_text,
        )
    if args.bank is not None:
        observation = observation.__class__(
            bank_cents=dollars_to_cents(args.bank),
            vault_cents=observation.vault_cents,
            card_value_cents=observation.card_value_cents,
            raw_text=observation.raw_text,
        )
    print("region text:")
    print(observation.raw_text)
    print()
    print(f"bank: {cents_to_dollars(observation.bank_cents) if observation.bank_cents is not None else 'unknown'}")
    print(f"vault: {cents_to_dollars(observation.vault_cents) if observation.vault_cents is not None else 'unknown'}")
    print(
        "card value: "
        f"{cents_to_dollars(observation.card_value_cents) if observation.card_value_cents is not None else 'unknown'}"
    )
    print(f"advice: {advice_from_observation(observation)}")
    return 0


def command_advise_screen(args: argparse.Namespace) -> int:
    regions = load_regions(args.regions)
    field_sets = {
        "pack": {"bank"},
        "result": {"revealed_card_value"},
        "buyback": {"buyback_offer"},
    }
    selected = {
        name: region
        for name, region in regions.items()
        if name in field_sets[args.state]
    }
    observation = observation_from_regions(args.image, selected)
    bank = dollars_to_cents(args.bank) if args.bank is not None else observation.bank_cents

    if args.state == "pack":
        if bank is None:
            print("action: wait")
            print("reason: bank value was not measurable")
            return 0
        if args.pack_price is None:
            print("action: wait")
            print("reason: --pack-price is required for pack-state advice")
            return 0
        pack_price = dollars_to_cents(args.pack_price)
        min_bank = dollars_to_cents(args.min_bank)
        if bank - pack_price < min_bank:
            print("action: stop")
            print(
                "reason: buying would leave "
                f"{cents_to_dollars(bank - pack_price)}, below floor "
                f"{cents_to_dollars(min_bank)}"
            )
        else:
            print("action: buy")
            print(
                "reason: bank after buy would be "
                f"{cents_to_dollars(bank - pack_price)}"
            )
        return 0

    if args.state == "result":
        if args.pack_price is None:
            print("action: wait")
            print("reason: --pack-price is required for result-state advice")
            return 0
        if observation.card_value_cents is None:
            print("action: wait")
            print("reason: revealed card value was not measurable")
            return 0
        pack_price = dollars_to_cents(args.pack_price)
        action = "vault" if observation.card_value_cents > pack_price else "sell"
        print(f"action: {action}")
        print(
            "reason: card "
            f"{cents_to_dollars(observation.card_value_cents)} vs pack cost "
            f"{cents_to_dollars(pack_price)}"
        )
        return 0

    if observation.card_value_cents is None:
        print("action: wait")
        print("reason: buyback amount was not measurable")
        return 0
    if args.expected_sell is not None:
        expected = dollars_to_cents(args.expected_sell)
        if observation.card_value_cents != expected:
            print("action: wait")
            print(
                "reason: buyback amount "
                f"{cents_to_dollars(observation.card_value_cents)} does not match expected "
                f"{cents_to_dollars(expected)}"
            )
            return 0
    print("action: accept")
    print(f"reason: buyback offer is {cents_to_dollars(observation.card_value_cents)}")
    return 0


def command_classify_screen(args: argparse.Namespace) -> int:
    try:
        state, text = classify_image(args.image)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"state: {state}")
    print("ocr text:")
    print(text.strip())
    return 0


def _load_session(path: Path) -> LiveSession:
    if not path.exists():
        raise FileNotFoundError(f"session not found: {path}; run session-start first")
    return load_live_session(path)


def _print_session(session: LiveSession) -> None:
    print(f"bank: {cents_to_dollars(session.bank_cents)}")
    print(f"vault: {cents_to_dollars(session.vault_cents)}")
    print(f"vault cards: {session.vault_count}")
    print(f"total tracked value: {cents_to_dollars(session.total_value_cents)}")
    print(f"cash floor: {cents_to_dollars(session.min_bank_cents)}")
    print(f"opened: {session.opened_count}")
    if session.pending is None:
        print("pending: none")
    else:
        print(f"pending: {session.pending.pack_id} at {cents_to_dollars(session.pending.pack_price_cents)}")
        if session.pending.card_value_cents is not None:
            print(f"pending card: {cents_to_dollars(session.pending.card_value_cents)}")
        if session.pending.advised_action is not None:
            print(f"pending action: {session.pending.advised_action}")


def _format_probability(value: float) -> str:
    return f"{value * 100:.1f}%"


def _pack_unlock_reason(
    session: LiveSession,
    pack,
    two_fifty_bank_cents: int,
) -> str | None:
    if pack.id == "two_fifty" and session.bank_cents < two_fifty_bank_cents:
        return (
            f"$2.50 pack unlocks at {cents_to_dollars(two_fifty_bank_cents)} bank; "
            f"current bank is {cents_to_dollars(session.bank_cents)}"
        )
    return None


def _print_pack_projection(
    session: LiveSession,
    pack,
    two_fifty_bank_cents: int | None = None,
) -> None:
    projection = project_pack_open(
        bank_cents=session.bank_cents,
        vault_cents=session.vault_cents,
        min_bank_cents=session.min_bank_cents,
        pack=pack,
    )
    print(f"pack: {projection.pack_name} ({projection.pack_id})")
    print(f"price: {cents_to_dollars(projection.price_cents)}")
    locked_reason = None
    if two_fifty_bank_cents is not None:
        locked_reason = _pack_unlock_reason(session, pack, two_fifty_bank_cents)
        if locked_reason is not None:
            print("mode: $1 fallback")
            print("action: use $1 pack")
            print(f"reason: {locked_reason}")
            print("projection if opened anyway:")
    if not projection.can_buy:
        print("action: stop")
        print(
            "reason: buying would leave "
            f"{cents_to_dollars(projection.bank_after_buy_cents)}, below floor "
            f"{cents_to_dollars(projection.min_bank_cents)}"
        )
        return

    if locked_reason is None:
        print("action: open manually if you accept the risk")
    print(f"bank after buy: {cents_to_dollars(projection.bank_after_buy_cents)}")
    print(f"expected card value: {cents_to_dollars(round(projection.expected_card_value_cents))}")
    print(f"expected card profit: {cents_to_dollars(round(projection.expected_card_profit_cents))}")
    print(f"expected bank after resolution: {cents_to_dollars(round(projection.expected_bank_after_cents))}")
    print(f"expected bank change: {cents_to_dollars(round(projection.expected_bank_delta_cents))}")
    print(f"expected total change: {cents_to_dollars(round(projection.expected_total_delta_cents))}")
    print(f"sell probability: {_format_probability(projection.sell_probability)}")
    print(f"vault probability: {_format_probability(projection.vault_probability)}")
    print(f"profit probability: {_format_probability(projection.total_profit_probability)}")
    print(
        "same-pack reopen probability: "
        f"{_format_probability(projection.can_open_same_pack_again_probability)}"
    )
    print(f"worst bank after resolution: {cents_to_dollars(projection.worst_bank_after_cents)}")
    print(f"best bank after resolution: {cents_to_dollars(projection.best_bank_after_cents)}")


def _log_committed_event(ledger: Path, event: dict[str, object]) -> None:
    append_ledger_record(ledger, event)
    print(f"logged: {ledger}")


def _read_money_from_screen(
    image: Path | None,
    manual_value: str | None,
    regions_path: Path,
    state: str,
) -> int | None:
    if bool(image) == bool(manual_value):
        raise ValueError("provide exactly one of --image or manual value")
    if manual_value is not None:
        return dollars_to_cents(manual_value)

    regions = load_regions(regions_path)
    wanted = {
        "result": {"revealed_card_value"},
        "buyback": {"buyback_offer"},
    }[state]
    observation = observation_from_regions(
        image,
        {name: region for name, region in regions.items() if name in wanted},
    )
    return observation.card_value_cents


def command_session_start(args: argparse.Namespace) -> int:
    if args.session.exists() and not args.force:
        print(f"session already exists: {args.session}", file=sys.stderr)
        print("use --force to overwrite it", file=sys.stderr)
        return 2

    session = start_live_session(
        bank_cents=dollars_to_cents(args.bank),
        vault_cents=dollars_to_cents(args.vault),
        min_bank_cents=dollars_to_cents(args.min_bank),
        vault_count=args.vault_count,
    )
    save_live_session(args.session, session)
    print(f"session: {args.session}")
    _print_session(session)
    return 0


def command_session_status(args: argparse.Namespace) -> int:
    try:
        session = _load_session(args.session)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _print_session(session)
    return 0


def command_session_recommend(args: argparse.Namespace) -> int:
    try:
        session = _load_session(args.session)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if session.pending is not None:
        print("recommendation: wait")
        print("reason: finish the pending pack result first")
        _print_session(session)
        return 0

    packs = load_packs(args.config)
    two_fifty_bank = dollars_to_cents(args.two_fifty_bank)
    pack = choose_bankroll_tier_pack(
        bank_cents=session.bank_cents,
        min_bank_cents=session.min_bank_cents,
        packs=packs,
        two_fifty_bank_cents=two_fifty_bank,
    )
    if pack is None:
        print("recommendation: stop")
        print("reason: no eligible pack keeps the bank floor")
        return 0

    print(f"recommendation: open {pack.name} ({pack.id})")
    if pack.id == "one_dollar" and session.bank_cents < two_fifty_bank:
        print(
            "tier: $1 fallback until bank reaches "
            f"{cents_to_dollars(two_fifty_bank)}"
        )
    elif pack.id == "two_fifty":
        print(f"tier: $2.50 unlocked at {cents_to_dollars(two_fifty_bank)}")
    _print_pack_projection(session, pack, two_fifty_bank)
    return 0


def command_session_plan(args: argparse.Namespace) -> int:
    try:
        session = _load_session(args.session)
        pack = find_pack(load_packs(args.config), args.pack)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if session.pending is not None:
        print("action: wait")
        print("reason: finish the pending pack result first")
        _print_session(session)
        return 0

    _print_pack_projection(session, pack, dollars_to_cents(args.two_fifty_bank))
    return 0


def command_session_buy(args: argparse.Namespace) -> int:
    try:
        session = _load_session(args.session)
        pack = find_pack(load_packs(args.config), args.pack)
        two_fifty_bank = dollars_to_cents(args.two_fifty_bank)
        locked_reason = _pack_unlock_reason(session, pack, two_fifty_bank)
        if locked_reason is not None:
            raise ValueError(locked_reason)
        _print_pack_projection(session, pack, two_fifty_bank)
        begin_pending_pack(session, pack.id, pack.price_cents)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    save_live_session(args.session, session)
    print(f"pending pack: {pack.name} ({pack.id})")
    print(f"bank after buy: {cents_to_dollars(session.bank_cents)}")
    return 0


def command_session_result(args: argparse.Namespace) -> int:
    try:
        session = _load_session(args.session)
        card_value = _read_money_from_screen(
            args.image,
            args.card_value,
            args.regions,
            "result",
        )
        if card_value is None:
            print("action: wait")
            print("reason: revealed card value was not measurable")
            return 0
        action = advise_pending_result(session, card_value, args.rarity_hint)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"card: {cents_to_dollars(card_value)}")
    print(f"vault: {cents_to_dollars(session.vault_cents)}")
    print(f"action: {action}")

    if action == "vault":
        if args.commit_vault:
            event = commit_vault(session)
            print(f"committed: {event['action']}")
            print(f"bank: {cents_to_dollars(session.bank_cents)}")
            print(f"vault: {cents_to_dollars(session.vault_cents)}")
            print(f"vault cards: {session.vault_count}")
            save_live_session(args.session, session)
            _log_committed_event(args.ledger, event)
            return 0
        else:
            print("next: tap Vault, then run session-vault")
    else:
        print("next: tap Sell, then run session-buyback on the buyback sheet")

    save_live_session(args.session, session)
    return 0


def command_session_buyback(args: argparse.Namespace) -> int:
    try:
        session = _load_session(args.session)
        amount = _read_money_from_screen(
            args.image,
            args.amount,
            args.regions,
            "buyback",
        )
        if amount is None:
            print("action: wait")
            print("reason: buyback amount was not measurable")
            return 0
        if session.pending is None or session.pending.expected_buyback_cents is None:
            raise ValueError("no pending sell buyback to confirm")
        if amount != session.pending.expected_buyback_cents:
            raise ValueError(
                "buyback amount "
                f"{cents_to_dollars(amount)} does not match expected "
                f"{cents_to_dollars(session.pending.expected_buyback_cents)}"
            )
        print("action: accept")
        print(f"buyback: {cents_to_dollars(amount)}")
        if args.commit:
            event = commit_buyback(session, amount)
            print(f"committed: {event['action']}")
            print(f"bank: {cents_to_dollars(session.bank_cents)}")
            save_live_session(args.session, session)
            _log_committed_event(args.ledger, event)
        else:
            print("next: tap Accept, then rerun this command with --commit")
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def command_session_vault(args: argparse.Namespace) -> int:
    try:
        session = _load_session(args.session)
        event = commit_vault(session)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    save_live_session(args.session, session)
    print(f"committed: {event['action']}")
    print(f"bank: {cents_to_dollars(session.bank_cents)}")
    print(f"vault: {cents_to_dollars(session.vault_cents)}")
    print(f"vault cards: {session.vault_count}")
    _log_committed_event(args.ledger, event)
    return 0


def command_session_screen(args: argparse.Namespace) -> int:
    try:
        session = _load_session(args.session)
        state = args.state
        if state == "auto":
            state, _ = classify_image(args.image)
            if state == "pack_style":
                print("screen: pack_style")
                print("action: apply or close")
                print("reason: this sheet changes pack odds/style, not bank/vault state")
                return 0
            if state == "unknown":
                print("screen: unknown")
                print("action: wait")
                print("reason: screenshot state could not be classified")
                return 0

        print(f"screen: {state}")
        if state == "pack":
            return _handle_session_pack_screen(args, session)
        if state == "result":
            return _handle_session_result_screen(args, session)
        if state == "buyback":
            return _handle_session_buyback_screen(args, session)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"unsupported screen state: {state}", file=sys.stderr)
    return 1


def _handle_session_pack_screen(args: argparse.Namespace, session: LiveSession) -> int:
    if session.pending is not None:
        print("action: wait")
        print("reason: finish the pending pack before buying another")
        return 0

    packs = load_packs(args.config)
    two_fifty_bank = dollars_to_cents(args.two_fifty_bank)
    if args.pack is None:
        pack = choose_bankroll_tier_pack(
            bank_cents=session.bank_cents,
            min_bank_cents=session.min_bank_cents,
            packs=packs,
            two_fifty_bank_cents=two_fifty_bank,
        )
    else:
        pack = find_pack(packs, args.pack)
        locked_reason = _pack_unlock_reason(session, pack, two_fifty_bank)
        if locked_reason is not None:
            print("action: use $1 pack")
            print(f"reason: {locked_reason}")
            return 0

    if pack is None:
        print("action: stop")
        print("reason: no eligible pack keeps the bank floor")
        return 0
    if session.bank_cents - pack.price_cents < session.min_bank_cents:
        print("action: stop")
        print(
            "reason: buying "
            f"{pack.name} would leave {cents_to_dollars(session.bank_cents - pack.price_cents)}"
        )
        return 0

    print(f"action: buy {pack.name} ({pack.id})")
    _print_pack_projection(session, pack, two_fifty_bank)
    if args.commit:
        begin_pending_pack(session, pack.id, pack.price_cents)
        save_live_session(args.session, session)
        print("committed: pending pack started")
    else:
        print(f"next: buy in app, then run session-screen {args.image} --state pack --pack {pack.id} --commit")
    return 0


def _handle_session_result_screen(args: argparse.Namespace, session: LiveSession) -> int:
    card_value = _read_money_from_screen(args.image, None, args.regions, "result")
    if card_value is None:
        print("action: wait")
        print("reason: revealed card value was not measurable")
        return 0

    action = advise_pending_result(session, card_value, args.rarity_hint)
    print(f"card: {cents_to_dollars(card_value)}")
    print(f"vault: {cents_to_dollars(session.vault_cents)}")
    print(f"action: {action}")
    if action == "vault":
        if args.commit:
            event = commit_vault(session)
            save_live_session(args.session, session)
            print(f"committed: {event['action']}")
            print(f"bank: {cents_to_dollars(session.bank_cents)}")
            print(f"vault: {cents_to_dollars(session.vault_cents)}")
            print(f"vault cards: {session.vault_count}")
            _log_committed_event(args.ledger, event)
        else:
            save_live_session(args.session, session)
            print("next: tap Vault, then rerun this command with --commit")
    else:
        save_live_session(args.session, session)
        print("next: tap Sell, then use session-screen on the buyback sheet")
    return 0


def _handle_session_buyback_screen(args: argparse.Namespace, session: LiveSession) -> int:
    amount = _read_money_from_screen(args.image, None, args.regions, "buyback")
    if amount is None:
        print("action: wait")
        print("reason: buyback amount was not measurable")
        return 0
    if session.pending is None or session.pending.expected_buyback_cents is None:
        raise ValueError("no pending sell buyback to confirm")
    if amount != session.pending.expected_buyback_cents:
        raise ValueError(
            "buyback amount "
            f"{cents_to_dollars(amount)} does not match expected "
            f"{cents_to_dollars(session.pending.expected_buyback_cents)}"
        )

    print("action: accept")
    print(f"buyback: {cents_to_dollars(amount)}")
    if args.commit:
        event = commit_buyback(session, amount)
        save_live_session(args.session, session)
        print(f"committed: {event['action']}")
        print(f"bank: {cents_to_dollars(session.bank_cents)}")
        _log_committed_event(args.ledger, event)
    else:
        print("next: tap Accept, then rerun this command with --commit")
    return 0


def command_device_capture(args: argparse.Namespace) -> int:
    try:
        path = capture_screenshot(args.output, args.remote_path)
    except DeviceAccessError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"screenshot: {path}")
    return 0


def command_device_advise(args: argparse.Namespace) -> int:
    try:
        image = capture_screenshot(args.output, args.remote_path)
    except DeviceAccessError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    screen_args = argparse.Namespace(
        image=image,
        regions=args.regions,
        state=args.state,
        pack_price=args.pack_price,
        bank=args.bank,
        vault=args.vault,
        min_bank=args.min_bank,
        expected_sell=args.expected_sell,
    )
    print(f"screenshot: {image}")
    return command_advise_screen(screen_args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    commands = {
        "simulate": command_simulate,
        "recommend": command_recommend,
        "record": command_record,
        "analyze-ledger": command_analyze_ledger,
        "export-ledger-config": command_export_ledger_config,
        "advise-text": command_advise_text,
        "read-screen": command_read_screen,
        "read-regions": command_read_regions,
        "advise-screen": command_advise_screen,
        "classify-screen": command_classify_screen,
        "session-start": command_session_start,
        "session-status": command_session_status,
        "session-recommend": command_session_recommend,
        "session-plan": command_session_plan,
        "session-buy": command_session_buy,
        "session-result": command_session_result,
        "session-buyback": command_session_buyback,
        "session-vault": command_session_vault,
        "session-screen": command_session_screen,
        "device-capture": command_device_capture,
        "device-advise": command_device_advise,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
