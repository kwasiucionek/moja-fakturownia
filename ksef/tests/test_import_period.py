from datetime import date

from django.test import SimpleTestCase

from ksef.ksef2_import import import_period, month_windows


class KsefImportPeriodTests(SimpleTestCase):
    def test_explicit_period_split_by_month(self):
        start, end = import_period(
            date_from=date(2026, 3, 15), date_to=date(2026, 5, 2)
        )
        windows = month_windows(start, end)
        self.assertEqual(
            [(a.date(), b.date()) for a, b in windows],
            [
                (date(2026, 3, 15), date(2026, 3, 31)),
                (date(2026, 4, 1), date(2026, 4, 30)),
                (date(2026, 5, 1), date(2026, 5, 2)),
            ],
        )

    def test_year_boundary_and_invalid_range(self):
        start, end = import_period(
            date_from=date(2025, 12, 20), date_to=date(2026, 1, 5)
        )
        self.assertEqual(len(month_windows(start, end)), 2)
        with self.assertRaises(ValueError):
            import_period(date_from=date(2026, 5, 1), date_to=date(2026, 4, 1))
