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


class EwpImportedSettlementsTests(TestCase):
    """Rozliczenia z importu JPK_EWP: sam przychód, bez wpłat i zaliczek."""

    def setUp(self):
        self.user = User.objects.create_user("ewa", password="x")
        CompanyInfo.objects.create(
            user=self.user,
            company_name="Firma",
            tax_id="1234567890",
            street="Ulica 1",
            zip_code="00-001",
            city="Wrocław",
            bank_account_number="00",
            lump_sum_rate="14",
            zus_health_insurance_only=True,
        )
        contractor = Contractor.objects.create(
            user=self.user, name="Szpital", tax_id="1111111111"
        )
        make_invoice(self.user, contractor, "1/2026", date(2026, 1, 15), "10000")
        for month, revenue in ((1, "10000"), (2, "20000")):
            MonthlySettlement.objects.create(
                user=self.user,
                year=2026,
                month=month,
                total_revenue=D(revenue),
                health_insurance_paid=0,
                income_tax_payable=0,
                status="imported",
                revenue_from_ewp=True,
            )

    def test_revenue_from_ewp_and_assumed_payments(self):
        r = settlements.monthly_obligations(self.user, 2026, 2)
        # luty: brak faktur, ale ewidencja ma 20 000 zł
        self.assertEqual(r["przychod"]["razem"], D("20000"))
        self.assertEqual(r["przychod"]["z_faktur"], D("0"))
        self.assertEqual(r["przychod"]["zrodlo"], settlements.REVENUE_SOURCE_EWP)
        # wpłata zdrowotnej przyjęta (styczniowa należna), a nie 0 z importu
        self.assertEqual(
            r["ryczalt_za_miesiac"]["skladka_zdrowotna_zaplacona_w_miesiacu"],
            D("498.35"),
        )
        self.assertTrue(any("różni się od faktur" in n for n in r["uwagi"]))

    def test_annual_uses_computed_advances_for_imported_months(self):
        r = settlements.annual_settlement(self.user, 2026)
        self.assertEqual(r["przychod"]["razem"], D("30000"))
        self.assertGreater(r["pit28"]["zaplacone_zaliczki"], D("0"))
        self.assertTrue(any("importu JPK_EWP" in n for n in r["uwagi"]))

    def test_completeness_flags_ewp_vs_invoices(self):
        issues = settlements.completeness_checks(self.user, 2026, 2)
        self.assertTrue(any("JPK_EWP" in i["opis"] for i in issues))
        self.assertFalse(
            any(
                "JPK_EWP" in i["opis"]
                for i in settlements.completeness_checks(self.user, 2026, 1)
            )
        )

    def test_draft_replaces_import_and_keeps_ewp_revenue(self):
        s, created, _ = settlements.save_monthly_settlement(self.user, 2026, 2)
        self.assertFalse(created)
        s.refresh_from_db()
        self.assertEqual(s.status, "draft")
        self.assertTrue(s.revenue_from_ewp)
        self.assertEqual(s.total_revenue, D("20000"))
        self.assertEqual(s.health_insurance_paid, D("498.35"))


class PreviousYearHealthReconciliationTests(TestCase):
    """Dopłata z rocznego rozliczenia zdrowotnej za rok poprzedni — zapłacona w maju."""

    def setUp(self):
        self.user = User.objects.create_user("ola", password="x")
        CompanyInfo.objects.create(
            user=self.user,
            company_name="Firma",
            tax_id="1234567890",
            street="Ulica 1",
            zip_code="00-001",
            city="Wrocław",
            bank_account_number="00",
            lump_sum_rate="14",
            zus_health_insurance_only=True,
        )
        c = Contractor.objects.create(user=self.user, name="Szpital", tax_id="111")
        # 2025: próg 60 tys. przekroczony w lutym -> styczeń płacony z niższego progu
        make_invoice(self.user, c, "1/2025", date(2025, 1, 31), "30000")
        make_invoice(self.user, c, "2/2025", date(2025, 2, 28), "40000")
        for month in range(1, 5):
            make_invoice(self.user, c, f"{month}/2026", date(2026, month, 28), "10000")
        make_invoice(self.user, c, "6/2026", date(2026, 6, 30), "37060")

    def test_previous_year_top_up(self):
        amount, notes = settlements.previous_year_health_reconciliation(self.user, 2026)
        # 12 × 769,43 − (461,66 + 11 × 769,43) = 307,77
        self.assertEqual(amount, D("307.77"))
        self.assertTrue(notes)

    def test_top_up_counts_as_paid_in_may_and_carries_to_june(self):
        r = settlements.monthly_obligations(self.user, 2026, 6)
        may = settlements.year_breakdown(self.user, 2026, 5)["months"][-1]
        # w maju: składka za kwiecień (498,35) + dopłata za 2025 (307,77)
        self.assertEqual(may["health_paid"], D("806.12"))
        # maj bez przychodu -> 403,06 przechodzi na czerwiec
        lump = r["ryczalt_za_miesiac"]
        self.assertEqual(lump["odliczenia_z_poprzednich_miesiecy"], D("403.06"))
        self.assertTrue(any("dopłatę z rocznego rozliczenia" in n for n in r["uwagi"]))

    def test_annual_includes_top_up_in_paid_health(self):
        with_top_up = settlements.annual_settlement(self.user, 2026)
        without = settlements.annual_settlement(
            self.user, 2026, include_prev_reconciliation=False
        )
        self.assertEqual(
            with_top_up["pit28"]["skladka_zdrowotna_zaplacona"]
            - without["pit28"]["skladka_zdrowotna_zaplacona"],
            D("307.77"),
        )


class BusinessSuspensionTests(TestCase):
    """Zawieszenie działalności: brak składek za pełne miesiące zawieszenia."""

    def setUp(self):
        from ksiegowosc.models import BusinessSuspension

        self.Suspension = BusinessSuspension
        self.user = User.objects.create_user("zawieszony", password="x")
        CompanyInfo.objects.create(
            user=self.user,
            company_name="Firma",
            tax_id="1234567890",
            street="Ulica 1",
            zip_code="00-001",
            city="Wrocław",
            bank_account_number="00",
            lump_sum_rate="14",
            zus_health_insurance_only=True,
        )
        c = Contractor.objects.create(user=self.user, name="Szpital", tax_id="111")
        # 2025: próg 60 tys. przekroczony w lutym -> dopłata za 2025 = 307,77 zł
        make_invoice(self.user, c, "1/2025", date(2025, 1, 31), "30000")
        make_invoice(self.user, c, "2/2025", date(2025, 2, 28), "40000")
        for month in range(1, 5):
            make_invoice(self.user, c, f"{month}/2026", date(2026, month, 28), "10000")
        make_invoice(self.user, c, "6/2026", date(2026, 6, 30), "37060")

    def test_full_month_suspension(self):
        self.Suspension.objects.create(
            user=self.user, date_from=date(2026, 5, 1), date_to=date(2026, 5, 31)
        )
        may = settlements.monthly_obligations(self.user, 2026, 5)
        self.assertEqual(may["zus_za_miesiac"]["razem_do_zaplaty"], D("0"))
        self.assertTrue(may["zawieszenie"]["caly_miesiac"])
        # w maju zapłacono kwiecień (498,35) + dopłatę za 2025 (307,77)
        self.assertEqual(
            may["ryczalt_za_miesiac"]["skladka_zdrowotna_zaplacona_w_miesiacu"],
            D("806.12"),
        )
        june = settlements.monthly_obligations(self.user, 2026, 6)
        lump = june["ryczalt_za_miesiac"]
        # w czerwcu nie płaci się składki za zawieszony maj
        self.assertEqual(lump["skladka_zdrowotna_zaplacona_w_miesiacu"], D("0"))
        self.assertEqual(lump["odliczenia_z_poprzednich_miesiecy"], D("403.06"))
        # (37 060 − 403,06) × 14% = 5 131,98 -> 5 132
        self.assertEqual(lump["podatek"], D("5132"))

    def test_annual_health_counts_only_active_months(self):
        self.Suspension.objects.create(
            user=self.user, date_from=date(2026, 5, 1), date_to=date(2026, 5, 31)
        )
        health = settlements.annual_settlement(self.user, 2026)["zdrowotna_roczna"]
        self.assertEqual(health["miesiace_dzialalnosci"], 11)
        self.assertEqual(health["miesiace_zawieszenia"], [5])

    def test_partial_suspension_keeps_full_health(self):
        self.Suspension.objects.create(
            user=self.user, date_from=date(2026, 5, 10), date_to=date(2026, 5, 31)
        )
        may = settlements.monthly_obligations(self.user, 2026, 5)
        self.assertFalse(may["zawieszenie"]["caly_miesiac"])
        self.assertEqual(may["zus_za_miesiac"]["zdrowotna"]["skladka"], D("498.35"))

    def test_invoice_in_suspended_month_is_flagged(self):
        self.Suspension.objects.create(
            user=self.user, date_from=date(2026, 6, 1), date_to=None
        )
        issues = settlements.completeness_checks(self.user, 2026, 6)
        self.assertTrue(any("zawieszenia" in i["opis"] for i in issues))
