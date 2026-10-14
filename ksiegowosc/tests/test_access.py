"""Konto bez danych firmy: brak pętli przekierowań i wyjście ze strony 403."""

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse


class NoCompanyInfoAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("test", password="haslo-testowe-123")
        # Jak konto „test” na produkcji: personel bez grup i uprawnień
        self.user.groups.clear()
        self.user.user_permissions.clear()
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)

    def test_no_redirect_loop_without_permissions(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("auth:dashboard"))
        self.assertRedirects(response, reverse("admin:index"))

    def test_403_page_offers_logout(self):
        response = self.client.get(reverse("admin:ksiegowosc_companyinfo_add"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, reverse("auth:logout"), status_code=403)
        self.assertContains(response, "test", status_code=403)

    def test_user_with_permission_is_sent_to_company_form(self):
        fresh = User.objects.create_user(
            "nowy", password="haslo-testowe-123", is_staff=True
        )
        fresh.user_permissions.add(Permission.objects.get(codename="add_companyinfo"))
        self.client.force_login(fresh)
        response = self.client.get(reverse("admin:index"))
        self.assertRedirects(
            response,
            reverse("admin:ksiegowosc_companyinfo_add"),
            fetch_redirect_response=False,
        )
