#!/usr/bin/env python3
"""Render a compact profile card from GitHub's public contribution calendar."""

from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape


PROFILE = "J-Teste"
ROOT = Path(__file__).resolve().parents[2]
MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


class CalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.total_text: list[str] = []
        self.day_dates: dict[str, date] = {}
        self.day_counts: dict[str, int] = {}
        self._in_total = False
        self._tooltip_id: str | None = None
        self._tooltip_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "h2" and attributes.get("id") == "js-contribution-activity-description":
            self._in_total = True
        if tag == "td" and (day_id := attributes.get("id", "")).startswith("contribution-day-component-"):
            if raw_date := attributes.get("data-date"):
                self.day_dates[day_id] = date.fromisoformat(raw_date)
        if tag == "tool-tip" and (day_id := attributes.get("for", "")).startswith("contribution-day-component-"):
            self._tooltip_id = day_id
            self._tooltip_text = []

    def handle_data(self, data: str) -> None:
        if self._in_total:
            self.total_text.append(data)
        if self._tooltip_id:
            self._tooltip_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._in_total = False
        if tag == "tool-tip" and self._tooltip_id:
            label = " ".join(self._tooltip_text).strip()
            match = re.match(r"^(No|[\d,]+) contributions? on ", label)
            if not match:
                raise ValueError(f"Unrecognized contribution label: {label!r}")
            raw_count = match.group(1)
            self.day_counts[self._tooltip_id] = 0 if raw_count == "No" else int(raw_count.replace(",", ""))
            self._tooltip_id = None

    def metrics(self) -> tuple[int, int, date, date]:
        label = " ".join(self.total_text)
        match = re.search(r"([\d,\s\u202f]+)\s+contributions", label)
        if not match:
            raise ValueError(f"Contribution total not found: {label!r}")
        total = int(re.sub(r"\D", "", match.group(1)))
        if len(self.day_dates) < 350 or self.day_dates.keys() != self.day_counts.keys():
            raise ValueError("Contribution calendar is incomplete")
        if sum(self.day_counts.values()) != total:
            raise ValueError("Daily counts do not match the displayed total")
        return total, sum(count > 0 for count in self.day_counts.values()), min(self.day_dates.values()), max(self.day_dates.values())


def fetch_metrics() -> tuple[int, int, date, date]:
    request = Request(
        f"https://github.com/users/{PROFILE}/contributions",
        headers={
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": "J-Teste-profile-metrics/1.0",
        },
    )
    with urlopen(request, timeout=20) as response:
        parser = CalendarParser()
        parser.feed(response.read().decode("utf-8"))
    return parser.metrics()


def card(total: int, active: int, start: date, end: date, mobile: bool) -> str:
    total_label = f"{total:,}".replace(",", " ")
    end_label = end.strftime("%d.%m.%Y")
    description = escape(
        f"Du {start.day} {MONTHS[start.month - 1]} {start.year} au "
        f"{end.day} {MONTHS[end.month - 1]} {end.year} : "
        f"{total_label} contributions GitHub et {active} jours actifs. "
        "Chiffres visibles sur le profil GitHub, actualisés automatiquement."
    )
    if mobile:
        width, height = 600, 350
        body = f"""<text x="32" y="47" fill="#d9cda4" font-size="21" letter-spacing="1">04 / ACTIVITÉ GITHUB</text>
<text x="568" y="47" fill="#aaa9ad" font-size="16" text-anchor="end">{end_label}</text>
<path d="M32 67h536" stroke="#363638"/>
<text x="30" y="163" fill="#f4f3ef" font-size="87" font-weight="600" letter-spacing="-3">{total_label}</text>
<text x="34" y="201" fill="#c7c7c8" font-size="25">contributions GitHub</text>
<path d="M32 223h536" stroke="#363638"/>
<text x="32" y="303" fill="#f4f3ef" font-size="67" font-weight="600" letter-spacing="-2">{active}</text>
<text x="223" y="299" fill="#c7c7c8" font-size="25">jours actifs</text>
<text x="34" y="332" fill="#aaa9ad" font-size="16">Sur les 12 derniers mois · chiffres visibles sur ce profil</text>"""
    else:
        width, height = 1100, 260
        body = f"""<text x="42" y="47" fill="#d9cda4" font-size="14" letter-spacing="1.7">04 / ACTIVITÉ GITHUB</text>
<text x="1058" y="47" fill="#aaa9ad" font-size="14" text-anchor="end">12 DERNIERS MOIS · {end_label}</text>
<text x="40" y="156" fill="#f4f3ef" font-size="94" font-weight="600" letter-spacing="-3.5">{total_label}</text>
<text x="45" y="195" fill="#c7c7c8" font-size="24">contributions GitHub</text>
<path d="M652 73v137" stroke="#363638"/>
<text x="711" y="155" fill="#f4f3ef" font-size="80" font-weight="600" letter-spacing="-2">{active}</text>
<text x="716" y="194" fill="#c7c7c8" font-size="23">jours actifs</text>
<path d="M42 219h1016" stroke="#363638"/>
<text x="43" y="245" fill="#aaa9ad" font-size="16">Contributions visibles sur ce profil · données GitHub actualisées automatiquement</text>"""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">Activité GitHub sur les 12 derniers mois</title>
<desc id="desc">{description}</desc>
<rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="18" fill="#111113" stroke="#343437"/>
<g font-family="Arial, Helvetica, sans-serif">
{body}
</g>
</svg>
"""


def main() -> None:
    total, active, start, end = fetch_metrics()
    (ROOT / "profile-metrics.svg").write_text(card(total, active, start, end, False), encoding="utf-8")
    (ROOT / "profile-metrics-mobile.svg").write_text(card(total, active, start, end, True), encoding="utf-8")
    print(f"{total} contributions, {active} active days, {start} to {end}")


if __name__ == "__main__":
    main()
