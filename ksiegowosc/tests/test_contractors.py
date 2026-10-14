"""Kontrahenci: normalizacja NIP-u, dopasowanie przy imporcie, scalanie duplikatów."""

import importlib
from datetime import date
from decimal import Decimal as D

from django.apps import apps
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory, SimpleTestCase, TestCase

from ksiegowosc.admin import ContractorAdmin
from ksiegowosc.contractors import (
    ContractorMergeError,
    find_or_create_contractor,
    merge_contractors,
    pick_merge_target,
)
from ksiegowosc.models import Contractor, DutyRate, Invoice, normalize_tax_id

from .test_settlements import make_invoice

RATES = {
    "rate_weekday_towarzyszacy": D("100"),
    "rate_weekday_samodzielny": D("120"),
    "rate_weekend_towarzyszacy": D("130"),
    "rate_weekend_samodzielny": D("150"),
}


class NormalizeTaxIdTests(SimpleTestCase):
    def test_formats(self):
        self.assertEqual(normalize_tax_id("691-21-31-539"), "6912131539")
        self.assertEqual(normalize_tax_id(" 691 213 15 39 "), "6912131539")
        self.assertEqual(normalize_tax_id("PL6912131539"), "6912131539")
        self.assertEqual(normalize_tax_id("pl 691-213-15-39"), "6912131539")
        self.assertEqual(normalize_tax_id("DE123456789"), "DE123456789")
        self.assertIsNone(normalize_tax_id(""))
        self.assertIsNone(normalize_tax_id(None))


class FindOrCreateContractorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("k", password="x")

    def test_same_nip_in_any_format(self):
        a, created_a = find_or_create_contractor(
            self.user, "691-21-31-539", "POGOTOWIE RATUNKOWE W LEGNICY"
        )
        b, created_b = find_or_create_contractor(
            self.user, "6912131539", "Pogotowie Ratunkowe w Legnicy"
        )
        self.assertTrue(created_a)
        self.assertFalse(created_b)
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(a.tax_id, "6912131539")

    def test_without_nip_matches_by_name(self):
        a, _ = find_or_create_contractor(
            self.user, "6912131539", "POGOTOWIE RATUNKOWE W LEGNICY"
        )
        b, created = find_or_create_contractor(
            self.user, None, "Pogotowie  Ratunkowe w Legnicy"
        )
        self.assertFalse(created)
        self.assertEqual(a.pk, b.pk)

    def test_nip_fills_contractor_created_without_nip(self):
        a, _ = find_or_create_contractor(
            self.user, None, "Pogotowie Ratunkowe w Legnicy"
        )
        self.assertIsNone(a.tax_id)
        b, created = find_or_create_contractor(
            self.user, "PL6912131539", "POGOTOWIE RATUNKOWE W LEGNICY"
        )
        self.assertFalse(created)
        self.assertEqual(b.pk, a.pk)
        a.refresh_from_db()
        self.assertEqual(a.tax_id, "6912131539")

    def test_name_filled_when_created_from_nip_only(self):
        a, _ = find_or_create_contractor(self.user, "8992227939", None)
        self.assertEqual(a.name, "8992227939")
        b, _ = find_or_create_contractor(self.user, "899-222-79-39", "Szpital")
        self.assertEqual(b.pk, a.pk)
        self.assertEqual(b.name, "Szpital")

    def test_admin_form_rejects_duplicate_with_dashes(self):
        Contractor.objects.create(user=self.user, name="A", tax_id="6912131539")
        request = RequestFactory().get("/")
        request.user = self.user
        Form = ContractorAdmin(Contractor, AdminSite()).get_form(request)
        form = Form(data={"name": "B", "tax_id": "691-21-31-539"})
        self.assertFalse(form.is_valid())
        self.assertIn("tax_id", form.errors)
        ok = Form(data={"name": "C", "tax_id": "899-222-79-39"})
        self.assertTrue(ok.is_valid())
        self.assertEqual(ok.cleaned_data["tax_id"], "8992227939")

    def test_model_clean_rejects_duplicate(self):
        Contractor.objects.create(user=self.user, name="A", tax_id="6912131539")
        dup = Contractor(user=self.user, name="B", tax_id="PL 691-213-15-39")
        with self.assertRaises(ValidationError):
            dup.full_clean()


class MergeContractorsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("k", password="x")
        self.a = Contractor.objects.create(
            user=self.user, name="Pogotowie", tax_id="6912131539"
        )
        self.b = Contractor.objects.create(
            user=self.user, name="Pogotowie", city="Legnica"
        )
        make_invoice(self.user, self.a, "1/2023", date(2023, 7, 31), "100")
        make_invoice(self.user, self.b, "2/2023", date(2023, 6, 30), "200")
        make_invoice(self.user, self.b, "3/2023", date(2023, 6, 30), "300")

    def test_merge_moves_invoices_and_fills_blanks(self):
        target = pick_merge_target([self.a, self.b])
        self.assertEqual(target.pk, self.a.pk)  # z NIP-em, mimo mniejszej liczby faktur
        moved = merge_contractors(target, [self.a, self.b])
        self.assertEqual(sum(moved.values()), 2)
        self.assertFalse(Contractor.objects.filter(pk=self.b.pk).exists())
        self.assertEqual(Invoice.objects.filter(contractor=self.a).count(), 3)
        self.a.refresh_from_db()
        self.assertEqual(self.a.city, "Legnica")

    def test_different_nips_refused(self):
        c = Contractor.objects.create(user=self.user, name="Inny", tax_id="8992227939")
        with self.assertRaises(ContractorMergeError):
            merge_contractors(self.a, [c])

    def test_duty_rate_clash_refused(self):
        DutyRate.objects.create(
            user=self.user, contractor=self.a, valid_from=date(2026, 1, 1), **RATES
        )
        DutyRate.objects.create(
            user=self.user, contractor=self.b, valid_from=date(2026, 1, 1), **RATES
        )
        with self.assertRaises(ContractorMergeError):
            merge_contractors(self.a, [self.b])
        self.assertTrue(Contractor.objects.filter(pk=self.b.pk).exists())

    def test_admin_action(self):
        request = RequestFactory().post("/")
        request.user = User.objects.create_superuser("admin", password="x")
        request._messages = _Messages()
        admin = ContractorAdmin(Contractor, AdminSite())
        admin.merge_selected(
            request, Contractor.objects.filter(pk__in=[self.a.pk, self.b.pk])
        )
        self.assertEqual(Contractor.objects.filter(user=self.user).count(), 1)
        self.assertIn("Scalono 1", request._messages.items[0])


class _Messages:
    def __init__(self):
        self.items = []

    def add(self, level, message, extra_tags=""):
        self.items.append(str(message))


class MergeMigrationTests(TestCase):
    """Migracja 0022 na danych jak w produkcji: NIP z myślnikami, bez nich i brak NIP-u."""

    def test_merges_legacy_duplicates(self):
        user = User.objects.create_user("k", password="x")
        # Zapis z pominięciem normalizacji w save() — tak jak dane sprzed poprawki
        dashed = Contractor.objects.create(
            user=user, name="POGOTOWIE RATUNKOWE W LEGNICY"
        )
        Contractor.objects.filter(pk=dashed.pk).update(tax_id="691-21-31-539")
        plain = Contractor.objects.create(
            user=user, name="POGOTOWIE RATUNKOWE W LEGNICY", tax_id="6912131539"
        )
        no_nip = Contractor.objects.create(
            user=user, name="Pogotowie Ratunkowe w Legnicy"
        )
        other = Contractor.objects.create(
            user=user, name="Szpital", tax_id="899-222-79-39"
        )
        Contractor.objects.filter(pk=other.pk).update(tax_id="899-222-79-39")
        for i, c in enumerate([dashed, dashed, plain, no_nip]):
            make_invoice(user, c, f"{i}/2023", date(2023, 6, 30), "100")

        migration = importlib.import_module(
            "ksiegowosc.migrations.0022_normalize_contractor_tax_id"
        )
        migration.merge_duplicates(apps, None)

        left = list(Contractor.objects.filter(user=user).order_by("pk"))
        self.assertEqual([c.pk for c in left], [dashed.pk, other.pk])
        self.assertEqual(left[0].tax_id, "6912131539")
        self.assertEqual(left[1].tax_id, "8992227939")
        self.assertEqual(Invoice.objects.filter(contractor=dashed).count(), 4)
