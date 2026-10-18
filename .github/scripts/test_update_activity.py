"""Regression checks for complete calendars and the rolling card window."""

import io
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import update_activity as activity


def year_counts(year, contributions=None):
    first = date(year, 1, 1)
    days = (date(year + 1, 1, 1) - first).days
    counts = {first + timedelta(days=offset): 0 for offset in range(days)}
    counts.update(contributions or {})
    return counts


def calendar_html(counts, total=None, missing_tooltip=None):
    if total is None:
        total = sum(counts.values())
    parts = [f'<h2 id="js-contribution-activity-description">{total:,} contributions</h2>']
    for offset, (day, count) in enumerate(sorted(counts.items())):
        day_id = f"contribution-day-component-{offset}"
        parts.append(f'<td id="{day_id}" data-date="{day}"></td>')
        if day != missing_tooltip:
            label = f"{count:,}" if count else "No"
            parts.append(f'<tool-tip for="{day_id}">{label} contributions on {day}.</tool-tip>')
    return "".join(parts).encode()


class ActivityTests(unittest.TestCase):
    def test_fetches_complete_years_and_keeps_exactly_365_days(self):
        previous = year_counts(2025, {date(2025, 10, 18): 4, date(2025, 10, 19): 1})
        current = year_counts(2026, {
            date(2026, 9, 12): 631,
            date(2026, 10, 18): 29,
            date(2026, 10, 19): 1000,  # Never include dates after the card's end.
        })
        with patch.object(activity, "datetime") as clock, patch.object(
            activity, "urlopen", side_effect=[
                io.BytesIO(calendar_html(previous)), io.BytesIO(calendar_html(current)),
            ],
        ) as fetch:
            clock.now.return_value = datetime(2026, 10, 18, tzinfo=ZoneInfo("Europe/Paris"))
            result = activity.fetch_metrics()
        self.assertEqual(result, (631, 3, date(2026, 9, 1), date(2025, 10, 19), date(2026, 10, 18)))
        self.assertEqual([call.args[0].full_url for call in fetch.call_args_list], [
            "https://github.com/users/J-Teste/contributions?from=2025-01-01&to=2025-12-31",
            "https://github.com/users/J-Teste/contributions?from=2026-01-01&to=2026-12-31",
        ])

    def test_inconsistent_source_totals_still_fail(self):
        parser = activity.CalendarParser()
        parser.feed(calendar_html(year_counts(2026), total=4).decode())
        with self.assertRaisesRegex(ValueError, "do not match"):
            parser.daily_counts()

    def test_missing_daily_tooltip_still_fails(self):
        parser = activity.CalendarParser()
        parser.feed(calendar_html(year_counts(2026), missing_tooltip=date(2026, 9, 1)).decode())
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parser.daily_counts()

    def test_missing_zero_count_day_in_window_still_fails(self):
        counts = year_counts(2025) | year_counts(2026)
        del counts[date(2026, 9, 1)]
        with self.assertRaisesRegex(ValueError, "365 days"):
            activity.calculate_metrics(counts, date(2026, 10, 18))

    def test_new_year_leap_day_and_recent_month_tie(self):
        counts = year_counts(2024, {
            date(2024, 1, 2): 1000,  # Outside the 365-day window.
            date(2024, 2, 29): 1,
            date(2024, 11, 15): 7,
            date(2024, 12, 15): 7,
        }) | year_counts(2025)
        self.assertEqual(
            activity.calculate_metrics(counts, date(2025, 1, 1)),
            (7, 3, date(2024, 12, 1), date(2024, 1, 3), date(2025, 1, 1)),
        )


if __name__ == "__main__":
    unittest.main()
