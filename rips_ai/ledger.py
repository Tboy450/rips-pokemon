from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PackLedgerSummary:
    pack_id: str
    observations: int
    average_card_value_cents: int
    median_card_value_cents: int
    best_card_value_cents: int
    average_observed_profit_cents: int
    sell_count: int
    vault_count: int


def cents_label(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100}.{cents % 100:02d}"


def append_ledger_record(
    path: Path,
    record: Mapping[str, object],
    recorded_at: str | None = None,
) -> dict[str, object]:
    normalized = dict(record)
    normalized.setdefault("recorded_at", recorded_at or utc_now())

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized, sort_keys=True) + "\n")
    return normalized


def load_ledger_records(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def summarize_records_by_pack(
    records: list[Mapping[str, object]],
) -> list[PackLedgerSummary]:
    by_pack: dict[str, list[Mapping[str, object]]] = {}
    for record in records:
        by_pack.setdefault(str(record["pack_id"]), []).append(record)

    summaries: list[PackLedgerSummary] = []
    for pack_id, pack_records in sorted(by_pack.items()):
        card_values = [int(record["card_value_cents"]) for record in pack_records]
        observed_profits = [
            int(record["card_value_cents"]) - int(record["pack_price_cents"])
            for record in pack_records
        ]
        summaries.append(
            PackLedgerSummary(
                pack_id=pack_id,
                observations=len(pack_records),
                average_card_value_cents=round(statistics.mean(card_values)),
                median_card_value_cents=round(statistics.median(card_values)),
                best_card_value_cents=max(card_values),
                average_observed_profit_cents=round(statistics.mean(observed_profits)),
                sell_count=sum(1 for record in pack_records if record.get("action") == "sell"),
                vault_count=sum(1 for record in pack_records if record.get("action") == "vault"),
            )
        )
    return summaries


def build_observed_pack_config(
    records: list[Mapping[str, object]],
    pack_names: Mapping[str, str] | None = None,
) -> dict[str, object]:
    names = pack_names or {}
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for record in records:
        grouped.setdefault(str(record["pack_id"]), []).append(record)

    packs: list[dict[str, object]] = []
    for pack_id, pack_records in sorted(grouped.items()):
        prices = {int(record["pack_price_cents"]) for record in pack_records}
        if len(prices) != 1:
            raise ValueError(f"pack {pack_id!r} has inconsistent observed prices")

        value_counts: dict[int, int] = {}
        for record in pack_records:
            value = int(record["card_value_cents"])
            value_counts[value] = value_counts.get(value, 0) + 1

        packs.append(
            {
                "id": pack_id,
                "name": names.get(pack_id, pack_id.replace("_", " ")),
                "price_cents": prices.pop(),
                "observations": len(pack_records),
                "outcomes": [
                    {
                        "value_cents": value,
                        "weight": count,
                        "label": f"observed {cents_label(value)}",
                    }
                    for value, count in sorted(value_counts.items())
                ],
            }
        )

    return {
        "notes": (
            "Built from observed ledger results. Outcome weights are raw "
            "observation counts, not guaranteed odds."
        ),
        "packs": packs,
    }
