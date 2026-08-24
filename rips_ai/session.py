from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .core import Action, cents_to_dollars


@dataclass
class PendingPack:
    pack_id: str
    pack_price_cents: int
    bank_before_cents: int
    vault_before_cents: int
    vault_count_before: int = 0
    card_value_cents: int | None = None
    advised_action: Action | None = None
    expected_buyback_cents: int | None = None
    rarity_hint: str | None = None


@dataclass
class LiveSession:
    bank_cents: int
    vault_cents: int = 0
    vault_count: int = 0
    min_bank_cents: int = 1000
    opened_count: int = 0
    pending: PendingPack | None = None
    history: list[dict[str, object]] = field(default_factory=list)

    @property
    def total_value_cents(self) -> int:
        return self.bank_cents + self.vault_cents

    def can_buy(self, price_cents: int) -> bool:
        return self.pending is None and self.bank_cents - price_cents >= self.min_bank_cents


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_live_session(path: Path) -> LiveSession:
    raw = json.loads(path.read_text(encoding="utf-8"))
    pending = raw.get("pending")
    vault_cents = int(raw.get("vault_cents", 0))
    return LiveSession(
        bank_cents=int(raw["bank_cents"]),
        vault_cents=vault_cents,
        vault_count=int(raw.get("vault_count", 1 if vault_cents > 0 else 0)),
        min_bank_cents=int(raw.get("min_bank_cents", 1000)),
        opened_count=int(raw.get("opened_count", 0)),
        pending=PendingPack(**pending) if pending else None,
        history=list(raw.get("history", [])),
    )


def save_live_session(path: Path, session: LiveSession) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(session), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def start_live_session(
    bank_cents: int,
    vault_cents: int,
    min_bank_cents: int,
    vault_count: int = 0,
) -> LiveSession:
    return LiveSession(
        bank_cents=bank_cents,
        vault_cents=vault_cents,
        vault_count=vault_count,
        min_bank_cents=min_bank_cents,
    )


def commit_bank_reconciliation(
    session: LiveSession,
    observed_bank_cents: int,
    source: str | None = None,
) -> dict[str, object]:
    previous_bank_cents = session.bank_cents
    session.bank_cents = observed_bank_cents
    event = {
        "recorded_at": utc_now(),
        "type": "bank_reconciliation",
        "source": source,
        "bank_before_cents": previous_bank_cents,
        "observed_bank_cents": observed_bank_cents,
        "bank_delta_cents": observed_bank_cents - previous_bank_cents,
        "pending_pack_id": None if session.pending is None else session.pending.pack_id,
    }
    session.history.append(event)
    return event


def commit_vault_audit(
    session: LiveSession,
    observed_vault_cents: int,
    observed_vault_count: int,
    source: str | None = None,
) -> dict[str, object]:
    previous_vault_cents = session.vault_cents
    previous_vault_count = session.vault_count
    session.vault_cents = observed_vault_cents
    session.vault_count = observed_vault_count
    event = {
        "recorded_at": utc_now(),
        "type": "vault_audit",
        "source": source,
        "vault_before_cents": previous_vault_cents,
        "vault_before_count": previous_vault_count,
        "observed_vault_cents": observed_vault_cents,
        "observed_vault_count": observed_vault_count,
        "vault_delta_cents": observed_vault_cents - previous_vault_cents,
        "vault_count_delta": observed_vault_count - previous_vault_count,
        "pending_pack_id": None if session.pending is None else session.pending.pack_id,
    }
    session.history.append(event)
    return event


def begin_pending_pack(session: LiveSession, pack_id: str, pack_price_cents: int) -> None:
    if session.pending is not None:
        raise ValueError("session already has a pending pack result")
    if session.bank_cents - pack_price_cents < session.min_bank_cents:
        raise ValueError(
            "buying would leave "
            f"{cents_to_dollars(session.bank_cents - pack_price_cents)}, below floor "
            f"{cents_to_dollars(session.min_bank_cents)}"
        )

    session.pending = PendingPack(
        pack_id=pack_id,
        pack_price_cents=pack_price_cents,
        bank_before_cents=session.bank_cents,
        vault_before_cents=session.vault_cents,
        vault_count_before=session.vault_count,
    )
    session.bank_cents -= pack_price_cents


def advise_pending_result(
    session: LiveSession,
    card_value_cents: int,
    rarity_hint: str | None = None,
) -> Action:
    if session.pending is None:
        raise ValueError("no pending pack; run session-buy first")

    action: Action = (
        "vault"
        if card_value_cents > session.pending.pack_price_cents
        else "sell"
    )
    session.pending.card_value_cents = card_value_cents
    session.pending.advised_action = action
    session.pending.expected_buyback_cents = card_value_cents if action == "sell" else None
    if rarity_hint is not None:
        session.pending.rarity_hint = rarity_hint
    return action


def commit_vault(session: LiveSession) -> dict[str, object]:
    pending = _require_pending_result(session, "vault")
    assert pending.card_value_cents is not None

    session.vault_cents += pending.card_value_cents
    session.vault_count += 1
    event = _event(session, pending, "vault", 0)
    _finish_pending(session, event)
    return event


def commit_buyback(session: LiveSession, buyback_cents: int) -> dict[str, object]:
    pending = _require_pending_result(session, "sell")
    assert pending.expected_buyback_cents is not None

    if buyback_cents != pending.expected_buyback_cents:
        raise ValueError(
            "buyback amount "
            f"{cents_to_dollars(buyback_cents)} does not match expected "
            f"{cents_to_dollars(pending.expected_buyback_cents)}"
        )

    session.bank_cents += buyback_cents
    event = _event(session, pending, "sell", buyback_cents)
    _finish_pending(session, event)
    return event


def _require_pending_result(session: LiveSession, action: Action) -> PendingPack:
    if session.pending is None:
        raise ValueError("no pending pack")
    if session.pending.card_value_cents is None or session.pending.advised_action is None:
        raise ValueError("pending pack has no card result yet")
    if session.pending.advised_action != action:
        raise ValueError(
            f"pending result is {session.pending.advised_action}, not {action}"
        )
    return session.pending


def _finish_pending(session: LiveSession, event: dict[str, object]) -> None:
    session.opened_count += 1
    session.history.append(event)
    session.pending = None


def _event(
    session: LiveSession,
    pending: PendingPack,
    action: Action,
    realized_cents: int,
) -> dict[str, object]:
    assert pending.card_value_cents is not None
    return {
        "recorded_at": utc_now(),
        "pack_id": pending.pack_id,
        "pack_price_cents": pending.pack_price_cents,
        "card_value_cents": pending.card_value_cents,
        "action": action,
        "realized_cents": realized_cents,
        "bank_return_cents": realized_cents,
        "bank_after_buy_cents": pending.bank_before_cents - pending.pack_price_cents,
        "bank_before_cents": pending.bank_before_cents,
        "vault_before_cents": pending.vault_before_cents,
        "vault_count_before": pending.vault_count_before,
        "bank_after_cents": session.bank_cents,
        "vault_after_cents": session.vault_cents,
        "vault_count_after": session.vault_count,
        "total_after_cents": session.total_value_cents,
        "total_before_cents": pending.bank_before_cents + pending.vault_before_cents,
        "bank_delta_cents": session.bank_cents - pending.bank_before_cents,
        "total_delta_cents": session.total_value_cents
        - (pending.bank_before_cents + pending.vault_before_cents),
        "rarity_hint": pending.rarity_hint,
    }
