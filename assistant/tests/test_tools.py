from datetime import date
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from assistant import tools
from assistant.agents import close_month
from assistant.models import ApiToken, AssistantReport
from ksiegowosc.models import CompanyInfo, Contractor, MonthlySettlement
from ksiegowosc.tests.test_settlements import make_invoice

RW = ("read", "write")


def make_company(user, **extra):
    data = dict(
        user=user,
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
    data.update(extra)
    return CompanyInfo.objects.create(**data)


class ToolsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("jan", password="x")
        make_company(self.user)
        self.contractor = Contractor.objects.create(
            user=self.user, name="Szpital", tax_id="1111111111"
        )
        make_invoice(self.user, self.contractor, "1/2026", date(2026, 1, 15), "10000")

    def test_read_tools_return_jsonable_data(self):
        self.assertEqual(
            tools.company_profile(self.user)["wariant_zus"], "tylko składka zdrowotna"
        )
        r = tools.revenue_summary(self.user, 2026, 1)
        self.assertEqual(r["przychod_razem"], "10000.00")
        r = tools.monthly_obligations(self.user, 2026, 1)
        self.assertEqual(r["ryczalt_za_miesiac"]["podatek"], "1368")
        self.assertEqual(r["zus_za_miesiac"]["termin"], "2026-02-20")
        r = tools.list_invoices(self.user, "2026-01-01", "2026-01-31")
        self.assertEqual(r["liczba"], 1)

    def test_bad_input_is_reported(self):
        with self.assertRaises(tools.ToolInputError):
            tools.monthly_obligations(self.user, 2026, 13)
        with self.assertRaises(tools.ToolInputError):
            tools.list_invoices(self.user, "13-01-2026", "2026-01-31")
        with self.assertRaises(tools.ToolInputError):
            tools.monthly_obligations(self.user, 2031, 1)  # brak parametrów roku

    def test_write_requires_scope_and_confirmation(self):
        with self.assertRaises(tools.ToolInputError):
            tools.save_monthly_settlement(self.user, 2026, 1, scopes=("read",))
        preview = tools.save_monthly_settlement(self.user, 2026, 1, scopes=RW)
        self.assertFalse(preview["zapisano"])
        self.assertFalse(MonthlySettlement.objects.exists())
        saved = tools.save_monthly_settlement(
            self.user, 2026, 1, confirm=True, scopes=RW
        )
        self.assertTrue(saved["zapisano"])
        self.assertEqual(MonthlySettlement.objects.get().status, "draft")
        tools.approve_monthly_settlement(self.user, 2026, 1, confirm=True, scopes=RW)
        self.assertEqual(MonthlySettlement.objects.get().status, "approved")
        with self.assertRaises(tools.ToolInputError):
            tools.save_monthly_settlement(self.user, 2026, 1, confirm=True, scopes=RW)

    def test_isolation_between_users(self):
        other = User.objects.create_user("ola", password="x")
        make_company(other)
        self.assertEqual(
            tools.revenue_summary(other, 2026, 1)["przychod_razem"], "0.00"
        )
        self.assertEqual(
            tools.list_invoices(other, "2026-01-01", "2026-12-31")["liczba"], 0
        )


class AgentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("jan", password="x")
        make_company(self.user)
        contractor = Contractor.objects.create(
            user=self.user, name="Szpital", tax_id="1111111111"
        )
        make_invoice(self.user, contractor, "1/2026", date(2026, 1, 15), "10000")

    def test_close_month_creates_draft_and_single_report(self):
        report = close_month(self.user, 2026, 1)
        self.assertIn("ryczałt 1 368,00 zł", report.title)
        self.assertIn("498,35 zł", report.content)
        self.assertEqual(MonthlySettlement.objects.get().status, "draft")
        close_month(self.user, 2026, 1)  # powtórne uruchomienie nie dubluje
        self.assertEqual(AssistantReport.objects.count(), 1)

    def test_close_month_keeps_approved_settlement(self):
        MonthlySettlement.objects.create(
            user=self.user,
            year=2026,
            month=1,
            total_revenue=D("10000"),
            health_insurance_paid=D("0"),
            income_tax_payable=D("1400"),
            status="approved",
        )
        report = close_month(self.user, 2026, 1)
        self.assertIn("już zatwierdzone", report.content)
        self.assertEqual(MonthlySettlement.objects.get().income_tax_payable, D("1400"))

    def test_management_command(self):
        call_command(
            "close_month",
            "--year",
            "2026",
            "--month",
            "1",
            stdout=open("/dev/null", "w"),
        )
        self.assertEqual(AssistantReport.objects.count(), 1)


class ApiTokenTests(TestCase):
    def test_issue_resolve_revoke(self):
        user = User.objects.create_user("jan", password="x")
        token, raw = ApiToken.issue(user, "test", can_write=True)
        self.assertTrue(raw.startswith("fk_"))
        self.assertNotIn(raw, token.token_hash)
        self.assertEqual(ApiToken.resolve(raw), token)
        self.assertIsNone(ApiToken.resolve(raw + "x"))
        token.revoke()
        self.assertIsNone(ApiToken.resolve(raw))


class RunMonthCloseViewTests(TestCase):
    def test_button_runs_agent_and_redirects_to_report(self):
        user = User.objects.create_superuser("szef", "s@example.com", "x")
        make_company(user)
        self.client.force_login(user)
        url = "/admin/assistant/assistantreport/uruchom-zamkniecie/"
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, {"year": "2026", "month": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(AssistantReport.objects.count(), 1)
        self.assertFalse(MonthlySettlement.objects.exists())  # bez szkicu
