"""Widoki rozliczeń w panelu korzystają z silnika obliczeń."""

from datetime import date
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase

from ksiegowosc.models import (
    CompanyInfo,
    Contractor,
    MonthlySettlement,
    YearlySettlement,
)
from ksiegowosc.tests.test_settlements import make_invoice


class SettlementAdminViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", "a@example.com", "x")
        CompanyInfo.objects.create(
            user=self.user,
            company_name="Firma",
            tax_id="1234567890",
            street="Ulica 1",
            zip_code="00-001",
            city="Wrocław",
            bank_account_number="00",
            lump_sum_rate="12",
            zus_health_insurance_only=True,
        )
        contractor = Contractor.objects.create(
            user=self.user, name="Klient", tax_id="1111111111"
        )
        make_invoice(
            self.user, contractor, "1/2026", date(2026, 1, 15), "10000", rate="12"
        )
        self.client.force_login(self.user)

    def test_monthly_view_uses_item_rate_not_hardcoded_14(self):
        url = "/admin/ksiegowosc/monthlysettlement/oblicz/"
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(
            url,
            {
                "year": "2026",
                "month": "1",
                "social_insurance_paid": "0",
                "labor_fund_paid": "0",
                "health_insurance_paid": "461,66",
            },
        )
        self.assertEqual(r.status_code, 200)
        s = MonthlySettlement.objects.get(year=2026, month=1)
        # (10000 - 230,83) * 12% = 1172,30 -> 1172 (a nie 14%)
        self.assertEqual(s.income_tax_payable, D("1172"))
        self.assertEqual(s.status, "approved")

    def test_yearly_view(self):
        url = "/admin/ksiegowosc/yearlysettlement/oblicz-roczne/"
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, {"year": "2026", "notes": ""})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(YearlySettlement.objects.filter(year=2026).exists())

    def test_zus_calculator_uses_engine(self):
        r = self.client.get(
            "/admin/ksiegowosc/monthlysettlement/kalkulator-zus/?year=2026"
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "498,35")  # próg do 60 tys. — przychód 10 tys.
        self.assertContains(r, "1495,04")
        r = self.client.get(
            "/admin/ksiegowosc/monthlysettlement/kalkulator-zus/?year=2030"
        )
        self.assertContains(r, "Brak parametrów")
