from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal

from .core import cents_to_dollars, decide_revealed_card, dollars_to_cents


ScreenState = Literal[
    "pack",
    "pack_style",
    "pack_picker",
    "whats_inside",
    "result",
    "buyback",
    "vault_gallery",
    "vault_appraisal",
    "unknown",
]
MONEY_RE = re.compile(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*|[0-9]+)(?:\.(\d{1,2}))?")


@dataclass(frozen=True)
class ScreenObservation:
    bank_cents: int | None = None
    vault_cents: int | None = None
    card_value_cents: int | None = None
    raw_text: str = ""

    def missing_fields(self) -> list[str]:
        missing = []
        if self.bank_cents is None:
            missing.append("bank")
        if self.vault_cents is None:
            missing.append("vault")
        if self.card_value_cents is None:
            missing.append("card_value")
        return missing


@dataclass(frozen=True)
class Region:
    name: str
    x: int
    y: int
    width: int
    height: int
    psm: int = 7
    whitelist: str | None = "$0123456789."
    scale: int = 2


def normalize_ocr_text(text: str) -> str:
    text = text.replace("＄", "$")
    text = text.replace("S", "$")
    text = text.replace("USD", "$")
    return re.sub(r"[ \t]+", " ", text)


def extract_money_cents(text: str) -> list[int]:
    values: list[int] = []
    for match in MONEY_RE.finditer(normalize_ocr_text(text)):
        whole = match.group(1).replace(",", "")
        fraction = match.group(2) or "00"
        fraction = fraction[:2].ljust(2, "0")
        values.append(dollars_to_cents(f"{whole}.{fraction}"))
    return values


def _extract_labeled_money(text: str, labels: tuple[str, ...]) -> int | None:
    lines = [line.strip() for line in normalize_ocr_text(text).splitlines() if line.strip()]
    label_pattern = "|".join(re.escape(label) for label in labels)
    inline_re = re.compile(
        rf"(?:{label_pattern})[^0-9$]{{0,24}}({MONEY_RE.pattern})",
        flags=re.IGNORECASE,
    )

    for line in lines:
        match = inline_re.search(line)
        if match:
            return extract_money_cents(match.group(1))[0]

    for index, line in enumerate(lines[:-1]):
        if any(label.lower() in line.lower() for label in labels):
            values = extract_money_cents(lines[index + 1])
            if values:
                return values[0]

    return None


def observation_from_text(text: str) -> ScreenObservation:
    normalized = normalize_ocr_text(text)
    bank = _extract_labeled_money(
        normalized,
        ("bank", "balance", "cash", "wallet"),
    )
    vault = _extract_labeled_money(
        normalized,
        ("vault", "collection", "kept"),
    )
    card = _extract_labeled_money(
        normalized,
        ("sell", "value", "card value", "market", "cash out"),
    )
    return ScreenObservation(
        bank_cents=bank,
        vault_cents=vault,
        card_value_cents=card,
        raw_text=text,
    )


def classify_screen_text(text: str) -> ScreenState:
    normalized = text.replace("＄", "$").lower()
    compact = re.sub(r"\s+", " ", normalized)
    if "accept buyback offer" in compact or "buyback offer" in compact:
        return "buyback"
    if "estimated payout odds" in compact or "choose your pack style" in compact:
        return "pack_style"
    if "tap to select a pack to open" in compact:
        return "pack_picker"
    if "sell" in compact and "vault" in compact:
        return "result"
    if "my collection" in compact or ("collection" in compact and "price" in compact):
        return "vault_gallery"
    if "appraisal" in compact or "appraised value" in compact:
        return "vault_appraisal"
    if "buy for" in compact or ("what's inside" in compact and "max pull" in compact):
        return "pack"
    if "what's inside" in compact:
        return "whats_inside"
    return "unknown"


def ocr_image(image_path: Path) -> str:
    tesseract = shutil.which("tesseract")
    if tesseract is None:
        raise RuntimeError(
            "No OCR engine is installed. Install tesseract or use the text/manual "
            "advisor until Shizuku UI dumps or screenshot OCR are available."
        )
    completed = subprocess.run(
        [tesseract, str(image_path), "stdout", "--psm", "6"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "tesseract OCR failed")
    return completed.stdout


def classify_image(image_path: Path) -> tuple[ScreenState, str]:
    text = ocr_image(image_path)
    return classify_screen_text(text), text


def _region_from_config(
    name: str,
    item: dict[str, object],
    source_width: int,
    source_height: int,
) -> Region:
    use_pixels = bool(item.get("pixels", False))
    if use_pixels:
        x = int(item["x"])
        y = int(item["y"])
        width = int(item["width"])
        height = int(item["height"])
    else:
        x = round(float(item["x"]) * source_width)
        y = round(float(item["y"]) * source_height)
        width = round(float(item["width"]) * source_width)
        height = round(float(item["height"]) * source_height)
    whitelist = item.get("whitelist", "$0123456789.")
    return Region(
        name=name,
        x=x,
        y=y,
        width=width,
        height=height,
        psm=int(item.get("psm", 7)),
        whitelist=None if whitelist is None else str(whitelist),
        scale=int(item.get("scale", 2)),
    )


def load_regions(path: Path) -> dict[str, Region]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    source = raw.get("source", {})
    source_width = int(source.get("width", 1080))
    source_height = int(source.get("height", 2340))
    regions = raw.get("regions", {})
    return {
        name: _region_from_config(name, item, source_width, source_height)
        for name, item in regions.items()
    }


def crop_region(image_path: Path, region: Region, output_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required for region OCR cropping")
    output_width = region.width * region.scale
    output_height = region.height * region.scale
    vf = (
        f"crop={region.width}:{region.height}:{region.x}:{region.y},"
        f"scale={output_width}:{output_height}"
    )
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(image_path),
            "-vf",
            vf,
            "-frames:v",
            "1",
            "-update",
            "1",
            str(output_path),
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "ffmpeg crop failed")


def ocr_image_region(image_path: Path, region: Region) -> str:
    tesseract = shutil.which("tesseract")
    if tesseract is None:
        raise RuntimeError("tesseract is required for OCR")

    with tempfile.TemporaryDirectory(prefix="rips-ocr-") as temp_dir:
        crop_path = Path(temp_dir) / f"{region.name}.jpg"
        crop_region(image_path, region, crop_path)
        command = [tesseract, str(crop_path), "stdout", "--psm", str(region.psm)]
        if region.whitelist:
            command.extend(["-c", f"tessedit_char_whitelist={region.whitelist}"])
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "tesseract region OCR failed")
    return completed.stdout.strip()


def observation_from_regions(
    image_path: Path,
    regions: dict[str, Region],
) -> ScreenObservation:
    texts: dict[str, str] = {}
    for name in ("bank", "vault", "revealed_card_value", "buyback_offer"):
        region = regions.get(name)
        if region is not None:
            texts[name] = ocr_image_region(image_path, region)

    def first_money(name: str) -> int | None:
        values = extract_money_cents(texts.get(name, ""))
        return values[0] if values else None

    card_value = first_money("revealed_card_value")
    if card_value is None:
        card_value = first_money("buyback_offer")

    return ScreenObservation(
        bank_cents=first_money("bank"),
        vault_cents=first_money("vault"),
        card_value_cents=card_value,
        raw_text="\n".join(f"{key}: {value}" for key, value in texts.items()),
    )


def advice_from_observation(observation: ScreenObservation) -> str:
    if observation.vault_cents is None or observation.card_value_cents is None:
        missing = ", ".join(observation.missing_fields())
        return f"cannot decide yet; missing measured field(s): {missing}"
    action = decide_revealed_card(observation.vault_cents, observation.card_value_cents)
    return (
        f"{action}: card {cents_to_dollars(observation.card_value_cents)} vs "
        f"vault {cents_to_dollars(observation.vault_cents)}"
    )
