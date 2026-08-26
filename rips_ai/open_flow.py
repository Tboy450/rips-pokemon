from __future__ import annotations

import json
from pathlib import Path

from .android_state import (
    return_to_package_commands,
    start_activity_commands,
    window_focus_probe_command,
)
from .vault import build_gallery_points

DEFAULT_FLOW_LABEL = "config/rips_android_flow.json"


def load_flow(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def gesture(flow: dict[str, object], name: str) -> dict[str, object]:
    gestures = flow.get("gestures", {})
    if not isinstance(gestures, dict) or name not in gestures:
        raise ValueError(f"gesture {name!r} was not found in {DEFAULT_FLOW_LABEL}")
    item = gestures[name]
    if not isinstance(item, dict):
        raise ValueError(f"gesture {name!r} is not an object")
    return item


def point(value: object, gesture_name: str) -> tuple[int, int]:
    if (
        not isinstance(value, list | tuple)
        or len(value) != 2
    ):
        raise ValueError(f"gesture {gesture_name!r} has an invalid point")
    return int(value[0]), int(value[1])


def parse_point_override(value: str | None, name: str) -> tuple[int, int] | None:
    if value is None:
        return None
    pieces = [piece.strip() for piece in value.split(",")]
    if len(pieces) != 2:
        raise ValueError(f"{name} must use X,Y format")
    try:
        return int(pieces[0]), int(pieces[1])
    except ValueError as exc:
        raise ValueError(f"{name} must use integer X,Y coordinates") from exc


def tap_command(
    flow: dict[str, object],
    name: str,
    override: tuple[int, int] | None = None,
) -> str:
    if override is not None:
        x, y = override
        return f"input tap {x} {y}"
    item = gesture(flow, name)
    x, y = point(item.get("at"), name)
    return f"input tap {x} {y}"


def swipe_command(flow: dict[str, object], name: str) -> str:
    item = gesture(flow, name)
    start_x, start_y = point(item.get("from"), name)
    end_x, end_y = point(item.get("to"), name)
    duration = int(item.get("duration_ms", 300))
    return f"input swipe {start_x} {start_y} {end_x} {end_y} {duration}"


def repeated_swipe_commands(flow: dict[str, object], name: str) -> list[str]:
    item = gesture(flow, name)
    repeat_count = max(1, int(item.get("repeat_count", 1)))
    repeat_delay = int(item.get("repeat_delay_ms", 0)) / 1000
    commands: list[str] = []
    for index in range(repeat_count):
        commands.append(swipe_command(flow, name))
        if index < repeat_count - 1 and repeat_delay > 0:
            commands.append(f"sleep {repeat_delay:.2f}")
    return commands


def gesture_delay_seconds(
    flow: dict[str, object],
    name: str,
    key: str,
    default_ms: int,
) -> float:
    return int(gesture(flow, name).get(key, default_ms)) / 1000


def open_pack_sequence(
    flow: dict[str, object],
    activity: str,
    return_package: str,
    stay_in_rips: bool,
    picker_spin: str,
    stage: str,
    buy_tap: tuple[int, int] | None = None,
) -> str:
    commands = start_activity_commands(activity)
    if stage in {"full", "tap-buy"}:
        commands.extend([tap_command(flow, "tap_buy", buy_tap), "sleep 3"])
    if stage == "tap-buy":
        if not stay_in_rips:
            commands.extend(return_to_package_commands(return_package))
        commands.append(window_focus_probe_command())
        return "; ".join(commands)

    if picker_spin in {"left", "both"}:
        commands.extend(
            [
                *repeated_swipe_commands(flow, "spin_picker_left"),
                f"sleep {gesture_delay_seconds(flow, 'spin_picker_left', 'settle_ms', 1200):.2f}",
            ]
        )
    if picker_spin in {"right", "both"}:
        commands.extend(
            [
                *repeated_swipe_commands(flow, "spin_picker_right"),
                f"sleep {gesture_delay_seconds(flow, 'spin_picker_right', 'settle_ms', 1200):.2f}",
            ]
        )
    commands.extend(
        [
            tap_command(flow, "tap_center_pack"),
            "sleep 0.8",
            swipe_command(flow, "slice_left_to_right"),
            f"sleep {gesture(flow, 'speed_up_reveal_swipe').get('delay_ms', 350) / 1000:.2f}",
            swipe_command(flow, "speed_up_reveal_swipe"),
            "sleep 5",
        ]
    )
    if not stay_in_rips:
        commands.extend(return_to_package_commands(return_package))
    commands.append(window_focus_probe_command())
    return "; ".join(commands)


def open_pack_dry_run_lines(
    *,
    stage: str,
    pack_name: str,
    pack_id: str,
    price: str,
    tracked_bank_before: str,
    planned_bank_after_buy: str,
    planned_pending: str,
    command: str,
    confirmed_buy_screen: bool,
    purchase_observed: bool,
) -> list[str]:
    lines = [
        "dry-run: device-open-pack",
        f"stage: {stage}",
        f"pack: {pack_name} ({pack_id})",
        f"price: {price}",
        f"tracked bank before: {tracked_bank_before}",
        f"planned bank after buy: {planned_bank_after_buy}",
        f"planned pending: {planned_pending}",
        "session mutation: none during dry run",
    ]
    if purchase_observed:
        lines.append("purchase observation: tracker would be allowed to mark pending")
    else:
        lines.append("purchase observation: not supplied; execution would not mutate tracker")
    if confirmed_buy_screen:
        lines.append("screen confirmation: main buy screen confirmed")
    else:
        lines.append("screen confirmation: execution still requires --confirmed-buy-screen")
    lines.append("shizuku sequence:")
    lines.extend(f"  {step}" for step in command.split("; "))
    return lines


def gallery_plan_parameters(
    flow: dict[str, object],
    *,
    columns: int | None = None,
    rows: int | None = None,
    pages: int | None = None,
    first_x: int | None = None,
    first_y: int | None = None,
    x_step: int | None = None,
    y_step: int | None = None,
    long_press_ms: int | None = None,
    between_cards_ms: int | None = None,
) -> tuple[dict[str, int], tuple[object, ...], str | None]:
    gallery = _vault_gallery_config(flow)
    resolved_first_x, resolved_first_y = _gallery_first_point(first_x, first_y, gallery)
    parameters = {
        "columns": _gallery_int_arg(columns, gallery, "columns", "--columns"),
        "rows": _gallery_int_arg(rows, gallery, "rows", "--rows"),
        "pages": _gallery_int_arg(pages, gallery, "pages", "--pages"),
        "first_x": resolved_first_x,
        "first_y": resolved_first_y,
        "x_step": _gallery_int_arg(x_step, gallery, "x_step", "--x-step"),
        "y_step": _gallery_int_arg(y_step, gallery, "y_step", "--y-step"),
        "long_press_ms": _gallery_int_arg(
            long_press_ms,
            gallery,
            "long_press_ms",
            "--long-press-ms",
        ),
        "between_cards_ms": _gallery_int_arg(
            between_cards_ms,
            gallery,
            "between_cards_ms",
            "--between-cards-ms",
        ),
    }
    points = build_gallery_points(
        columns=parameters["columns"],
        rows=parameters["rows"],
        pages=parameters["pages"],
        first_x=parameters["first_x"],
        first_y=parameters["first_y"],
        x_step=parameters["x_step"],
        y_step=parameters["y_step"],
    )
    scroll_command = optional_swipe_command(flow, "vault_gallery_scroll_next")
    return parameters, points, scroll_command


def gallery_shell_plan_lines(
    parameters: dict[str, int],
    points: tuple[object, ...],
    scroll_command: str | None,
) -> list[str]:
    lines: list[str] = []
    previous_page = 1
    for item in points:
        if item.page != previous_page:
            if scroll_command is None:
                lines.append(f"# Page {item.page}: scroll gesture is not configured")
            else:
                lines.extend(
                    [
                        "# Scroll to next gallery page",
                        scroll_command,
                        "sleep 0.8",
                    ]
                )
            previous_page = item.page
        lines.extend(
            [
                f"# Card {item.index}: page {item.page}, row {item.row}, column {item.column}",
                (
                    "input swipe "
                    f"{item.x} {item.y} {item.x} {item.y} {parameters['long_press_ms']}"
                ),
                "sleep 0.6",
                "# Read/write down the appraisal value now",
                "input keyevent BACK",
                f"sleep {parameters['between_cards_ms'] / 1000:.2f}",
            ]
        )
    return lines


def _vault_gallery_config(flow: dict[str, object]) -> dict[str, object]:
    gallery = flow.get("vault_gallery", {})
    if not isinstance(gallery, dict):
        return {}
    return gallery


def _gallery_int_arg(
    value: int | None,
    gallery: dict[str, object],
    key: str,
    flag_name: str,
) -> int:
    if value is not None:
        return int(value)
    if key not in gallery:
        raise ValueError(f"provide {flag_name} or set vault_gallery.{key}")
    return int(gallery[key])


def _gallery_first_point(
    first_x: int | None,
    first_y: int | None,
    gallery: dict[str, object],
) -> tuple[int, int]:
    if first_x is not None and first_y is not None:
        return first_x, first_y
    if first_x is not None or first_y is not None:
        raise ValueError("provide both --first-x and --first-y")

    item = gallery.get("first_card_center")
    if not isinstance(item, list | tuple) or len(item) != 2:
        raise ValueError("provide --first-x/--first-y or set vault_gallery.first_card_center")
    return int(item[0]), int(item[1])


def optional_swipe_command(flow: dict[str, object], name: str) -> str | None:
    try:
        return swipe_command(flow, name)
    except ValueError:
        return None
