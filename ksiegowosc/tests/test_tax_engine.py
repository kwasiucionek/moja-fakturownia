"""Testy silnika obliczeń — wartości referencyjne z komunikatów ZUS/GUS na 2025 i 2026 r."""

from datetime import date
from decimal import Decimal as D

from django.test import SimpleTestCase

from ksiegowosc.tax_engine import (
    ContributionProfile,
    MissingYearParams,
    UnsupportedTaxForm,
    annual_health_deadline,
    annual_return_deadline,
    health_contribution,
    lump_sum_deadline,
    lump_sum_health_contribution,
    lump_sum_tax,
    social_contributions,
    zus_deadline,
)
from ksiegowosc.tax_engine.calendar import easter_sunday, is_working_day


class SocialContributionsTests(SimpleTestCase):
    def test_full_2026_with_sickness(self):
        r = social_contributions(
            2026, ContributionProfile(zus_variant="full", sickness_insurance=True)
        )
        self.assertEqual(r.base, D("5652.00"))
        self.assertEqual(r.pension, D("1103.27"))
        self.assertEqual(r.disability, D("452.16"))
        self.assertEqual(r.sickness, D("138.47"))
        self.assertEqual(r.accident, D("94.39"))
        self.assertEqual(r.labor_fund, D("138.47"))
        self.assertEqual(r.total, D("1926.76"))

    def test_full_2026_without_sickness(self):
        r = social_contributions(2026, ContributionProfile(zus_variant="full"))
        self.assertEqual(r.total, D("1788.29"))
        self.assertEqual(r.social_total, D("1649.82"))

    def test_full_2025_with_sickness(self):
        r = social_contributions(
            2025, ContributionProfile(zus_variant="full", sickness_insurance=True)
        )
        self.assertEqual(r.base, D("5203.80"))
        self.assertEqual(r.total, D("1773.96"))

    def test_preferential_2025_and_2026(self):
        p = ContributionProfile(zus_variant="preferential", sickness_insurance=True)
        r25 = social_contributions(2025, p)
        self.assertEqual(r25.base, D("1399.80"))
        self.assertEqual(r25.total, D("442.90"))
        self.assertEqual(r25.labor_fund, D("0.00"))
        r26 = social_contributions(2026, p)
        self.assertEqual(r26.base, D("1441.80"))
        self.assertEqual(r26.disability, D("115.34"))
        self.assertEqual(r26.total, D("456.18"))

    def test_health_only_and_start_relief_have_no_social(self):
        for variant in ("health_only", "start_relief"):
            r = social_contributions(2026, ContributionProfile(zus_variant=variant))
            self.assertEqual(r.total, D("0.00"))

    def test_small_zus_plus_base_is_clamped_and_skips_labor_fund(self):
        low = social_contributions(
            2026,
            ContributionProfile(
                zus_variant="small_zus_plus", small_zus_plus_base=D("1000")
            ),
        )
        self.assertEqual(low.base, D("1441.80"))
        mid = social_contributions(
            2026,
            ContributionProfile(
                zus_variant="small_zus_plus", small_zus_plus_base=D("3000")
            ),
        )
        self.assertEqual(mid.base, D("3000.00"))
        self.assertEqual(mid.labor_fund, D("0.00"))
        with self.assertRaises(ValueError):
            social_contributions(
                2026, ContributionProfile(zus_variant="small_zus_plus")
            )

    def test_missing_year(self):
        with self.assertRaises(MissingYearParams):
            social_contributions(2030, ContributionProfile())


class HealthContributionTests(SimpleTestCase):
    def test_lump_sum_tiers_2026(self):
        cases = {
            D("0"): D("498.35"),
            D("60000"): D("498.35"),
            D("60000.01"): D("830.58"),
            D("300000"): D("830.58"),
            D("300000.01"): D("1495.04"),
        }
        for revenue, expected in cases.items():
            self.assertEqual(
                lump_sum_health_contribution(2026, revenue)["skladka"],
                expected,
                revenue,
            )

    def test_lump_sum_tiers_2025(self):
        self.assertEqual(
            lump_sum_health_contribution(2025, D("1000"))["skladka"], D("461.66")
        )
        self.assertEqual(
            lump_sum_health_contribution(2025, D("100000"))["skladka"], D("769.43")
        )
        self.assertEqual(
            lump_sum_health_contribution(2025, D("400000"))["skladka"], D("1384.97")
        )

    def test_other_tax_forms_not_supported_yet(self):
        with self.assertRaises(UnsupportedTaxForm):
            health_contribution(
                2026, ContributionProfile(tax_form="skala_podatkowa"), D("1000")
            )


class LumpSumTaxTests(SimpleTestCase):
    def test_single_rate_with_half_of_health(self):
        r = lump_sum_tax({D("14"): D("10000")}, health_paid=D("498.35"))
        self.assertEqual(r.bases[D("14")], D("9751"))
        self.assertEqual(r.tax, D("1365"))
        self.assertEqual(r.carry_forward, D("0.00"))

    def test_deductions_go_to_highest_rate_first(self):
        r = lump_sum_tax(
            {D("14"): D("1000"), D("8.5"): D("5000")}, social_paid=D("1500")
        )
        self.assertEqual(r.bases[D("14")], D("0"))
        self.assertEqual(r.bases[D("8.5")], D("4500"))
        self.assertEqual(r.tax, D("383"))

    def test_unused_deductions_carry_forward(self):
        r = lump_sum_tax({D("14"): D("100")}, social_paid=D("300"))
        self.assertEqual(r.tax, D("0"))
        self.assertEqual(r.carry_forward, D("200.00"))
        nxt = lump_sum_tax({D("14"): D("1000")}, carried_deductions=r.carry_forward)
        self.assertEqual(nxt.bases[D("14")], D("800"))
        self.assertEqual(nxt.tax, D("112"))

    def test_negative_correction_acts_as_deduction(self):
        r = lump_sum_tax({D("14"): D("-200"), D("8.5"): D("1000")})
        self.assertEqual(r.bases[D("8.5")], D("800"))
        self.assertEqual(r.tax, D("68"))


class DeadlineTests(SimpleTestCase):
    def test_holidays(self):
        self.assertEqual(easter_sunday(2026), date(2026, 4, 5))
        self.assertFalse(is_working_day(date(2026, 6, 4)))  # Boże Ciało
        self.assertFalse(is_working_day(date(2025, 12, 24)))  # Wigilia od 2025

    def test_zus_and_lump_sum_deadlines(self):
        self.assertEqual(zus_deadline(2026, 1), date(2026, 2, 20))
        self.assertEqual(zus_deadline(2026, 5), date(2026, 6, 22))  # 20.06 to sobota
        self.assertEqual(
            zus_deadline(2026, 11), date(2026, 12, 21)
        )  # 20.12 to niedziela
        self.assertEqual(lump_sum_deadline(2026, 3), date(2026, 4, 20))
        self.assertEqual(lump_sum_deadline(2025, 12), date(2026, 4, 30))

    def test_annual_deadlines(self):
        self.assertEqual(annual_return_deadline(2025), date(2026, 4, 30))
        self.assertEqual(annual_health_deadline(2025), date(2026, 5, 20))


class PartialMonthSocialTests(SimpleTestCase):
    def test_proportional_base_and_full_suspension(self):
        p = ContributionProfile(zus_variant="full")
        half = social_contributions(2026, p, active_days=15, days_in_month=30)
        self.assertEqual(half.base, D("2826.00"))
        self.assertGreater(half.labor_fund, D("0"))  # FP wg pełnej podstawy miesiąca
        none = social_contributions(2026, p, active_days=0, days_in_month=31)
        self.assertEqual(none.total, D("0.00"))
