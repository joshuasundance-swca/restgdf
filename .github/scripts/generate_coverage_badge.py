from __future__ import annotations

import json
import math
import sys
from pathlib import Path


LABEL = "coverage"
LABEL_WIDTH = 63
BADGE_HEIGHT = 20


def _read_percentage(path: Path) -> float:
    payload = json.loads(path.read_text(encoding="utf-8"))
    totals = payload["totals"]
    percent = totals.get("percent_covered")
    if percent is None:
        percent = float(str(totals["percent_covered_display"]).rstrip("%"))
    return float(percent)


def _format_percentage(percent: float) -> str:
    rounded = round(percent, 1)
    if math.isclose(rounded, round(rounded)):
        return f"{int(round(rounded))}%"
    return f"{rounded:.1f}%"


def _pick_color(percent: float) -> str:
    if percent >= 95:
        return "#4c1"
    if percent >= 90:
        return "#97ca00"
    if percent >= 80:
        return "#a4a61d"
    if percent >= 70:
        return "#dfb317"
    if percent >= 60:
        return "#fe7d37"
    return "#e05d44"


def _measure_text_width(text: str) -> int:
    return max(36, 10 + len(text) * 7)


def _build_svg(percent_text: str, color: str) -> str:
    value_width = _measure_text_width(percent_text)
    total_width = LABEL_WIDTH + value_width
    text_center_left = LABEL_WIDTH / 2
    text_center_right = LABEL_WIDTH + value_width / 2
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{BADGE_HEIGHT}">
    <linearGradient id="b" x2="0" y2="100%">
        <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
        <stop offset="1" stop-opacity=".1"/>
    </linearGradient>
    <mask id="a">
        <rect width="{total_width}" height="{BADGE_HEIGHT}" rx="3" fill="#fff"/>
    </mask>
    <g mask="url(#a)">
        <path fill="#555" d="M0 0h{LABEL_WIDTH}v{BADGE_HEIGHT}H0z"/>
        <path fill="{color}" d="M{LABEL_WIDTH} 0h{value_width}v{BADGE_HEIGHT}H{LABEL_WIDTH}z"/>
        <path fill="url(#b)" d="M0 0h{total_width}v{BADGE_HEIGHT}H0z"/>
    </g>
    <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
        <text x="{text_center_left}" y="15" fill="#010101" fill-opacity=".3">{LABEL}</text>
        <text x="{text_center_left}" y="14">{LABEL}</text>
        <text x="{text_center_right}" y="15" fill="#010101" fill-opacity=".3">{percent_text}</text>
        <text x="{text_center_right}" y="14">{percent_text}</text>
    </g>
</svg>
"""


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: generate_coverage_badge.py <coverage.json> <coverage.svg>",
            file=sys.stderr,
        )
        return 2

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    percent = _read_percentage(input_path)
    output_path.write_text(
        _build_svg(_format_percentage(percent), _pick_color(percent)),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
