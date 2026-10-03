#!/usr/bin/env python3
"""Render a compact profile card from GitHub's public contribution calendar."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo


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

    def metrics(self) -> tuple[int, int, date, date, date]:
        label = " ".join(self.total_text)
        match = re.search(r"([\d,\s\u202f]+)\s+contributions", label)
        if not match:
            raise ValueError(f"Contribution total not found: {label!r}")
        total = int(re.sub(r"\D", "", match.group(1)))
        if len(self.day_dates) < 350 or self.day_dates.keys() != self.day_counts.keys():
            raise ValueError("Contribution calendar is incomplete")
        if sum(self.day_counts.values()) != total:
            raise ValueError("Daily counts do not match the displayed total")
        today = datetime.now(ZoneInfo("Europe/Paris")).date()
        current_month = today.replace(day=1)
        end = max(self.day_dates.values())
        if end < current_month:
            raise ValueError("The current month is not yet in GitHub's calendar")
        end = min(end, today)
        recent_months = [current_month]
        for _ in range(2):
            recent_months.append((recent_months[-1] - timedelta(days=1)).replace(day=1))
        month_counts = {
            month: sum(
                count for day_id, count in self.day_counts.items()
                if month.year == self.day_dates[day_id].year
                and month.month == self.day_dates[day_id].month
                and self.day_dates[day_id] <= end
            )
            for month in recent_months
        }
        best_month = max(recent_months, key=lambda month: (month_counts[month], month))
        annual_start = end - timedelta(days=364)
        if min(self.day_dates.values()) > annual_start:
            raise ValueError("The contribution calendar does not cover the last 365 days")
        annual_active = sum(
            count > 0 for day_id, count in self.day_counts.items()
            if annual_start <= self.day_dates[day_id] <= end
        )
        return month_counts[best_month], annual_active, best_month, annual_start, end


def fetch_metrics() -> tuple[int, int, date, date, date]:
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


def card(total: int, active: int, best_month: date, annual_start: date, end: date, mobile: bool) -> str:
    total_label = f"{total:,}".replace(",", " ")
    end_label = end.strftime("%d.%m.%Y")
    month_label = MONTHS[best_month.month - 1]
    description = escape(
        f"Mois le plus actif des trois derniers mois : {total_label} contributions GitHub "
        f"en {month_label} {best_month.year}. "
        f"Du {annual_start.day} {MONTHS[annual_start.month - 1]} {annual_start.year} "
        f"au {end.day} {MONTHS[end.month - 1]} {end.year} : {active} jours actifs. "
        "Chiffres visibles sur le profil GitHub, actualisés automatiquement."
    )
    if mobile:
        width, height = 600, 440
        body = f"""<text x="32" y="47" fill="#d9cda4" font-size="21" letter-spacing="1">ACTIVITÉ GITHUB</text>
<text x="568" y="47" fill="#aaa9ad" font-size="16" text-anchor="end">{end_label}</text>
<text x="30" y="149" fill="#f4f3ef" font-size="87" font-weight="600" letter-spacing="-3">{total_label}</text>
<text x="34" y="189" fill="#c7c7c8" font-size="25">contributions en {month_label} {best_month.year}</text>
<text x="34" y="221" fill="#aaa9ad" font-size="22">Mois le plus actif des 3 derniers mois</text>
<path d="M32 245h536" stroke="#363638"/>
<text x="30" y="334" fill="#f4f3ef" font-size="87" font-weight="600" letter-spacing="-3">{active}</text>
<text x="34" y="374" fill="#c7c7c8" font-size="25">jours actifs</text>
<text x="34" y="409" fill="#aaa9ad" font-size="22">Sur les 12 derniers mois</text>"""
    else:
        width, height = 1100, 250
        body = f"""<text x="42" y="47" fill="#d9cda4" font-size="14" letter-spacing="1.7">ACTIVITÉ GITHUB</text>
<text x="1058" y="47" fill="#aaa9ad" font-size="14" text-anchor="end">Actualisé le {end_label}</text>
<text x="40" y="150" fill="#f4f3ef" font-size="94" font-weight="600" letter-spacing="-3.5">{total_label}</text>
<text x="45" y="189" fill="#c7c7c8" font-size="24">contributions en {month_label} {best_month.year}</text>
<text x="45" y="224" fill="#aaa9ad" font-size="18">Mois le plus actif des 3 derniers mois</text>
<path d="M652 73v151" stroke="#363638"/>
<text x="711" y="150" fill="#f4f3ef" font-size="94" font-weight="600" letter-spacing="-3.5">{active}</text>
<text x="716" y="189" fill="#c7c7c8" font-size="24">jours actifs</text>
<text x="716" y="224" fill="#aaa9ad" font-size="18">Sur les 12 derniers mois</text>"""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">Contributions du mois le plus actif et jours actifs sur les 12 derniers mois</title>
<desc id="desc">{description}</desc>
<rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="18" fill="#111113" stroke="#343437"/>
<g font-family="Arial, Helvetica, sans-serif">
{body}
</g>
</svg>
"""


def main() -> None:
    total, active, best_month, annual_start, end = fetch_metrics()
    desktop_svg = card(total, active, best_month, annual_start, end, False)
    mobile_svg = card(total, active, best_month, annual_start, end, True)
    version = hashlib.sha256((desktop_svg + mobile_svg).encode("utf-8")).hexdigest()[:12]

    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    for filename in ("profile-metrics.svg", "profile-metrics-mobile.svg"):
        pattern = re.compile(
            rf"(https://raw\.githubusercontent\.com/{PROFILE}/{PROFILE}/main/{filename}\?v=)[^\"\s>]+"
        )
        readme, replacements = pattern.subn(lambda match: match.group(1) + version, readme)
        if replacements != 1:
            raise ValueError(f"Expected one versioned URL for {filename}, found {replacements}")

    (ROOT / "profile-metrics.svg").write_text(desktop_svg, encoding="utf-8")
    (ROOT / "profile-metrics-mobile.svg").write_text(mobile_svg, encoding="utf-8")
    readme_path.write_text(readme, encoding="utf-8")
    print(f"{total} contributions in best recent month ({best_month}), {active} active days ({annual_start} to {end})")


if __name__ == "__main__":
    main()
