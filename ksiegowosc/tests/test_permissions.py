"""Zwykłe konta: uprawnienia z grupy „ksiegowosc”, izolacja danych, nazwa sekcji dyżurów."""

from datetime import date, time

from django.contrib.admin.sites import site
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from ksiegowosc.models import CompanyInfo, Contractor, DutyShift, PurchaseInvoice

PASSWORD = "haslo-testowe-123"


def make_company(user, **extra):
    return CompanyInfo.objects.create(
        user=user,
        company_name=f"Firma {user.username}",
        tax_id="1234567890",
        street="Ulica 1",
        zip_code="00-001",
        city="Wrocław",
        bank_account_number="00",
        **extra,
    )


class RegularUserAccessTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alicja", password=PASSWORD)
        self.bob = User.objects.create_user("bogdan", password=PASSWORD)
        make_company(self.alice)
        make_company(self.bob)
        self.c_alice = Contractor.objects.create(user=self.alice, name="Szpital Alicji")
        self.c_bob = Contractor.objects.create(
            user=self.bob, name="Przychodnia Bogdana"
        )
        for user, contractor in ((self.alice, self.c_alice), (self.bob, self.c_bob)):
            DutyShift.objects.create(
                user=user,
                contractor=contractor,
                date=date(2026, 10, 1),
                start_time=time(8),
                end_time=time(20),
            )
        self.client.force_login(self.alice)

    def test_new_account_gets_group_access(self):
        self.alice.refresh_from_db()
        self.assertTrue(self.alice.is_staff)
        self.assertTrue(self.alice.groups.filter(name="ksiegowosc").exists())
        for perm in (
            "ksiegowosc.view_dutyshift",
            "ksiegowosc.add_dutyrate",
            "ksiegowosc.view_purchaseinvoice",
            "ksiegowosc.add_businesssuspension",
            "assistant.view_assistantreport",
            "assistant.add_apitoken",
        ):
            self.assertTrue(self.alice.has_perm(perm), perm)
        self.assertFalse(self.alice.has_perm("auth.view_user"))
        self.assertFalse(self.alice.has_perm("ksiegowosc.change_zusrates"))

    def test_menu_contains_duties_and_assistant(self):
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, reverse("admin:ksiegowosc_dutyshift_changelist"))
        self.assertContains(response, reverse("admin:ksiegowosc_dutyrate_changelist"))
        self.assertContains(
            response, reverse("admin:assistant_assistantreport_changelist")
        )
        self.assertContains(response, reverse("admin:assistant_apitoken_changelist"))

    def test_lists_and_filters_show_only_own_data(self):
        response = self.client.get(reverse("admin:ksiegowosc_dutyshift_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Szpital Alicji")
        self.assertNotContains(
            response, "Przychodnia Bogdana"
        )  # ani na liście, ani w filtrze
        self.assertNotContains(response, "bogdan")  # brak filtra „Użytkownik”

    def test_foreign_key_choices_limited_to_own(self):
        request = RequestFactory().get("/")
        request.user = self.alice
        form = site._registry[PurchaseInvoice].get_form(request)()
        self.assertEqual(list(form.fields["supplier"].queryset), [self.c_alice])

    def test_second_company_info_not_allowed(self):
        response = self.client.get(reverse("admin:ksiegowosc_companyinfo_add"))
        self.assertEqual(response.status_code, 403)

    def test_custom_duty_module_name(self):
        CompanyInfo.objects.filter(user=self.alice).update(duty_module_name="Zlecenia")
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Zlecenia — stawki")
        response = self.client.get(reverse("admin:ksiegowosc_dutyshift_changelist"))
        self.assertContains(response, "Zlecenia")
        # inne konto widzi domyślną nazwę
        self.client.force_login(self.bob)
        response = self.client.get(reverse("admin:index"))
        self.assertNotContains(response, "Zlecenia")


class SuperuserUnaffectedTests(TestCase):
    def test_superuser_sees_user_filter(self):
        admin_user = User.objects.create_superuser("szef", password=PASSWORD)
        make_company(admin_user)
        other = User.objects.create_user("inny", password=PASSWORD)
        Contractor.objects.create(user=other, name="Cudzy kontrahent")
        self.client.force_login(admin_user)
        response = self.client.get(reverse("admin:ksiegowosc_contractor_changelist"))
        self.assertContains(response, "Cudzy kontrahent")
        self.assertFalse(admin_user.groups.exists())  # superuser nie trafia do grupy


class RegularUserScreensSmokeTests(TestCase):
    """Każdy ekran dostępny dla grupy „ksiegowosc” otwiera się bez błędu."""

    def test_changelists_and_add_forms(self):
        from ksiegowosc.permissions import GROUP_PERMISSIONS

        user = User.objects.create_user("zwykly", password=PASSWORD)
        make_company(user)
        self.client.force_login(user)
        for (app_label, model), actions in GROUP_PERMISSIONS.items():
            if model in ("invoiceitem", "purchaseinvoiceitem"):
                continue  # tylko jako pozycje w formularzu faktury
            url = reverse(f"admin:{app_label}_{model}_changelist")
            self.assertEqual(self.client.get(url).status_code, 200, url)
            if "add" in actions and model != "companyinfo":
                url = reverse(f"admin:{app_label}_{model}_add")
                self.assertEqual(self.client.get(url).status_code, 200, url)
