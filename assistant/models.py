import hashlib
import secrets

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

TOKEN_PREFIX = "fk_"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiTokenQuerySet(models.QuerySet):
    def active(self):
        return self.filter(revoked_at__isnull=True)


class ApiToken(models.Model):
    """Token dostępu do serwera MCP. W bazie trzymany jest tylko skrót SHA-256."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="api_tokens",
        verbose_name="Użytkownik",
    )
    name = models.CharField(
        max_length=100, verbose_name="Nazwa (np. Claude Code — laptop)"
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    prefix = models.CharField(
        max_length=12, editable=False, verbose_name="Początek tokena"
    )
    can_write = models.BooleanField(
        default=False,
        verbose_name="Zapis dozwolony",
        help_text="Pozwala zapisywać rozliczenia i importować z KSeF (zawsze z potwierdzeniem).",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Utworzono")
    last_used_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Ostatnie użycie"
    )
    revoked_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Unieważniono"
    )

    objects = ApiTokenQuerySet.as_manager()

    class Meta:
        verbose_name = "Token API (MCP)"
        verbose_name_plural = "Tokeny API (MCP)"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"

    @property
    def scopes(self) -> list[str]:
        return ["read", "write"] if self.can_write else ["read"]

    @classmethod
    def issue(cls, user, name: str, can_write: bool = False) -> tuple["ApiToken", str]:
        """Tworzy token i zwraca (obiekt, surowy token). Surowego tokena nie da się odtworzyć."""
        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token = cls.objects.create(
            user=user,
            name=name,
            can_write=can_write,
            token_hash=hash_token(raw),
            prefix=raw[:10],
        )
        return token, raw

    @classmethod
    def resolve(cls, raw: str) -> "ApiToken | None":
        if not raw or not raw.startswith(TOKEN_PREFIX):
            return None
        token = (
            cls.objects.active()
            .select_related("user")
            .filter(token_hash=hash_token(raw))
            .first()
        )
        if token is None or not token.user.is_active:
            return None
        cls.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
        return token

    def revoke(self):
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked_at"])


class AssistantReport(models.Model):
    """Raport agenta (np. zamknięcie miesiąca) do przejrzenia przez użytkownika."""

    KIND_CHOICES = [
        ("month_close", "Zamknięcie miesiąca"),
        ("annual", "Rozliczenie roczne"),
    ]
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="assistant_reports",
        verbose_name="Użytkownik",
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, verbose_name="Rodzaj")
    period = models.CharField(max_length=10, verbose_name="Okres")
    title = models.CharField(max_length=200, verbose_name="Tytuł")
    content = models.TextField(verbose_name="Treść (Markdown)")
    data = models.JSONField(default=dict, blank=True, verbose_name="Dane")
    has_issues = models.BooleanField(default=False, verbose_name="Wymaga uwagi")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Utworzono")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="Przeczytano")

    class Meta:
        verbose_name = "Raport asystenta"
        verbose_name_plural = "Raporty asystenta"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
