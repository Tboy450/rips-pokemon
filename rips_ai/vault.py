from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .core import dollars_to_cents


MONEY_TOKEN_RE = re.compile(r"\$?\s*\d+(?:\.\d{1,2})?")


@dataclass(frozen=True)
class GalleryPoint:
    index: int
    page: int
    row: int
    column: int
    x: int
    y: int


def parse_money_values(items: Iterable[str]) -> tuple[int, ...]:
    values: list[int] = []
    for item in items:
        for match in MONEY_TOKEN_RE.finditer(item):
            values.append(dollars_to_cents(match.group(0)))
    if not values:
        raise ValueError("no money values were provided")
    return tuple(values)


def build_gallery_points(
    *,
    columns: int,
    rows: int,
    first_x: int,
    first_y: int,
    x_step: int,
    y_step: int,
    pages: int = 1,
) -> tuple[GalleryPoint, ...]:
    if columns <= 0:
        raise ValueError("columns must be greater than 0")
    if rows <= 0:
        raise ValueError("rows must be greater than 0")
    if pages <= 0:
        raise ValueError("pages must be greater than 0")
    if x_step <= 0:
        raise ValueError("x-step must be greater than 0")
    if y_step <= 0:
        raise ValueError("y-step must be greater than 0")

    points: list[GalleryPoint] = []
    index = 1
    for page in range(1, pages + 1):
        for row in range(1, rows + 1):
            for column in range(1, columns + 1):
                points.append(
                    GalleryPoint(
                        index=index,
                        page=page,
                        row=row,
                        column=column,
                        x=first_x + ((column - 1) * x_step),
                        y=first_y + ((row - 1) * y_step),
                    )
                )
                index += 1
    return tuple(points)
