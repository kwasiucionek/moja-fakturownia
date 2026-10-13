"""Rozliczenia na danych z bazy — ryczałt 14%, tylko składka zdrowotna."""

from datetime import date
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase

from ksiegowosc import settlements
from ksiegowosc.models import (
    CompanyInfo,
    Contractor,
    Invoice,
    InvoiceItem,
    MonthlySettlement,
)


def make_invoice(user, contractor, number, day, amount, rate="14"):
    inv = Invoice.objects.create(
        user=user,
        invoice_number=number,
        issue_date=day,
        sale_date=day,
        contractor=contractor,
    )
    InvoiceItem.objects.create(
        user=user,
        invoice=inv,
        name="Usługa",
        quantity=D("1"),
        unit_price=D(amount),
        total_price=D(amount),
        lump_sum_tax_rate=D(rate),
    )
    return inv


class SettlementsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("jan", password="x")
        CompanyInfo.objects.create(
            user=self.user,
            company_name="Firma",
            tax_id="1234567890",
            street="Ulica 1",
            zip_code="00-001",
            city="Wrocław",
            bank_account_number="00",
            income_tax_type="ryczalt_ewidencjonowany",
            lump_sum_rate="14",
            zus_health_insurance_only=True,
        )
        self.contractor = Contractor.objects.create(
            user=self.user, name="Szpital", tax_id="1111111111"
        )
        make_invoice(self.user, self.contractor, "1/2026", date(2026, 1, 15), "10000")
        make_invoice(self.user, self.contractor, "2/2026", date(2026, 2, 10), "60000")

    def test_january(self):
        r = settlements.monthly_obligations(self.user, 2026, 1)
        self.assertEqual(r["przychod"]["razem"], D("10000"))
        self.assertEqual(r["zus_za_miesiac"]["spoleczne"]["razem"], D("0.00"))
        self.assertEqual(r["zus_za_miesiac"]["zdrowotna"]["skladka"], D("498.35"))
        # w styczniu zapłacono zdrowotną za grudzień 2025 (próg do 60 tys.)
        self.assertEqual(
            r["ryczalt_za_miesiac"]["skladka_zdrowotna_zaplacona_w_miesiacu"],
            D("461.66"),
        )
        self.assertEqual(r["ryczalt_za_miesiac"]["podatek"], D("1368"))
        self.assertEqual(r["ryczalt_za_miesiac"]["termin"], date(2026, 2, 20))

    def test_february_crosses_threshold(self):
        r = settlements.monthly_obligations(self.user, 2026, 2)
        self.assertEqual(r["przychod"]["narastajaco_od_poczatku_roku"], D("70000"))
        self.assertEqual(r["zus_za_miesiac"]["zdrowotna"]["skladka"], D("830.58"))
        self.assertEqual(r["ryczalt_za_miesiac"]["podatek"], D("8365"))

    def test_explicit_paid_amount_overrides_assumption(self):
        r = settlements.monthly_obligations(self.user, 2026, 1, health_paid=D("0"))
        self.assertEqual(r["ryczalt_za_miesiac"]["podatek"], D("1400"))

    def test_annual(self):
        r = settlements.annual_settlement(self.user, 2026)
        self.assertEqual(r["przychod"]["razem"], D("70000"))
        self.assertEqual(r["pit28"]["skladka_zdrowotna_zaplacona"], D("9265.81"))
        self.assertEqual(r["pit28"]["podatek"], D("9151"))
        self.assertEqual(r["pit28"]["zaplacone_zaliczki"], D("9733"))
        self.assertEqual(r["pit28"]["nadplata"], D("582"))
        self.assertEqual(r["zdrowotna_roczna"]["nalezna_za_rok"], D("9966.96"))
        self.assertEqual(r["zdrowotna_roczna"]["doplata"], D("332.23"))
        self.assertEqual(r["zdrowotna_roczna"]["termin"], date(2027, 5, 20))

    def test_save_draft_then_refuse_to_overwrite_approved(self):
        s, created, _ = settlements.save_monthly_settlement(self.user, 2026, 1)
        self.assertTrue(created)
        self.assertEqual(s.status, "draft")
        self.assertEqual(s.income_tax_payable, D("1368"))
        s.status = "approved"
        s.save()
        with self.assertRaises(settlements.SettlementError):
            settlements.save_monthly_settlement(self.user, 2026, 1)

    def test_saved_settlement_amounts_are_used(self):
        MonthlySettlement.objects.create(
            user=self.user,
            year=2026,
            month=1,
            total_revenue=D("10000"),
            health_insurance_paid=D("0"),
            social_insurance_paid=D("0"),
            income_tax_payable=D("1400"),
        )
        r = settlements.monthly_obligations(self.user, 2026, 1)
        self.assertEqual(r["ryczalt_za_miesiac"]["podatek"], D("1400"))

    def test_other_users_data_is_invisible(self):
        other = User.objects.create_user("obcy", password="x")
        with self.assertRaises(settlements.SettlementError):
            settlements.monthly_obligations(other, 2026, 1)

    def test_completeness_checks(self):
        issues = settlements.completeness_checks(self.user, 2026, 1)
        self.assertIsInstance(issues, list)
