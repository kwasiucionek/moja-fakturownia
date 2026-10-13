"""Serwer MCP Fakturowni — streamable HTTP (bezstanowy), uwierzytelnianie tokenem Bearer.

Uruchomienie: uvicorn assistant.mcp_server:app --host 127.0.0.1 --port 8501
Token: python manage.py create_api_token <użytkownik> --name "Claude Code" [--write]
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fakturownia.settings")
django.setup()

from decimal import Decimal  # noqa: E402
from typing import Annotated, Any, Literal  # noqa: E402

from asgiref.sync import sync_to_async  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from django.db import close_old_connections  # noqa: E402
from mcp.server.auth.middleware.auth_context import get_access_token  # noqa: E402
from mcp.server.auth.provider import AccessToken  # noqa: E402
from mcp.server.auth.settings import AuthSettings  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402
from pydantic import Field  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402

from assistant import tools  # noqa: E402
from assistant.models import ApiToken  # noqa: E402

PUBLIC_URL = os.environ.get("MCP_PUBLIC_URL", "http://127.0.0.1:8501").rstrip("/")
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("MCP_ALLOWED_HOSTS", "127.0.0.1:*,localhost:*").split(",")
    if h.strip()
]

INSTRUCTIONS = """\
Serwer księgowy aplikacji „Moja Fakturownia” (jednoosobowa działalność, ryczałt).
Daje dostęp do faktur, przychodów, składek ZUS, ryczałtu, rozliczenia rocznego, KSeF i dyżurów
zalogowanego użytkownika.

Zasady:
- Kwoty składek i podatku zawsze bierz z narzędzi — nie licz ich samodzielnie.
- Narzędzia zapisujące (save_*, approve_*, import_*) najpierw wywołuj bez confirm, pokaż
  użytkownikowi podgląd i dopiero po jego wyraźnej zgodzie wywołaj ponownie z confirm=true.
- Pole „uwagi” w wynikach opisuje założenia (np. przyjęte kwoty zapłaconych składek) —
  przekazuj je użytkownikowi.
- Kwoty są w złotych, daty w formacie RRRR-MM-DD.
"""


def _with_db(fn, *args, **kwargs):
    close_old_connections()
    try:
        return fn(*args, **kwargs)
    finally:
        close_old_connections()


class DjangoTokenVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        api_token = await sync_to_async(_with_db, thread_sensitive=True)(
            ApiToken.resolve, token
        )
        if api_token is None:
            return None
        return AccessToken(
            token=token,
            client_id=f"token-{api_token.pk}",
            scopes=api_token.scopes,
            subject=str(api_token.user_id),
        )


mcp = MCPServer(
    name="moja-fakturownia",
    title="Moja Fakturownia",
    instructions=INSTRUCTIONS,
    version="1.5.0",
    token_verifier=DjangoTokenVerifier(),
    auth=AuthSettings(
        issuer_url=PUBLIC_URL,
        resource_server_url=f"{PUBLIC_URL}/mcp",
        required_scopes=["read"],
        # Tokeny są nieprzezroczyste i wydawane tylko dla tego serwera (ApiToken)
        validate_token_resource=False,
    ),
)

READ = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
WRITE_EXTERNAL = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

Year = Annotated[int, Field(ge=2000, le=2100, description="Rok, np. 2026")]
Month = Annotated[int, Field(ge=1, le=12, description="Miesiąc 1–12")]
Money = Annotated[
    Decimal | None, Field(ge=0, description="Kwota w zł; pomiń, by użyć założenia")
]
Confirm = Annotated[
    bool,
    Field(description="false = tylko podgląd; true = wykonaj (po zgodzie użytkownika)"),
]


async def _call(fn, **kwargs) -> dict[str, Any]:
    access = get_access_token()
    if access is None or not access.subject:
        raise ToolError("Brak uwierzytelnienia.")

    def run():
        user = User.objects.get(pk=int(access.subject), is_active=True)
        return fn(user, scopes=tuple(access.scopes), **kwargs)

    try:
        return await sync_to_async(_with_db, thread_sensitive=True)(run)
    except tools.ToolInputError as exc:
        raise ToolError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Odczyt
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ)
async def company_profile() -> dict[str, Any]:
    """Dane firmy: forma opodatkowania, stawka ryczałtu, wariant ZUS, VAT, KSeF, uprawnienia tokena."""
    return await _call(tools.company_profile)


@mcp.tool(annotations=READ)
async def revenue_summary(year: Year, month: Month | None = None) -> dict[str, Any]:
    """Przychód za miesiąc lub cały rok: razem, wg stawek ryczałtu i wg kontrahentów."""
    return await _call(tools.revenue_summary, year=year, month=month)


@mcp.tool(annotations=READ)
async def list_invoices(
    date_from: Annotated[str, Field(description="Data od, RRRR-MM-DD")],
    date_to: Annotated[str, Field(description="Data do, RRRR-MM-DD")],
    contractor: Annotated[
        str | None, Field(description="Fragment nazwy kontrahenta")
    ] = None,
    payment_status: Annotated[
        Literal["opłacona", "nieopłacona", "przeterminowana", "częściowo"] | None,
        Field(description="Filtr statusu płatności"),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    """Faktury sprzedaży wystawione w okresie (z płatnościami i statusem KSeF)."""
    return await _call(
        tools.list_invoices,
        date_from=date_from,
        date_to=date_to,
        contractor=contractor,
        payment_status=payment_status,
        limit=limit,
    )


@mcp.tool(annotations=READ)
async def unpaid_invoices(overdue_only: bool = False) -> dict[str, Any]:
    """Nieopłacone (lub tylko przeterminowane) faktury sprzedaży z kwotą do zapłaty."""
    return await _call(tools.unpaid_invoices, overdue_only=overdue_only)


@mcp.tool(annotations=READ)
async def monthly_obligations(
    year: Year, month: Month, health_paid: Money = None, social_paid: Money = None
) -> dict[str, Any]:
    """Należności za miesiąc: składki ZUS (społeczne, zdrowotna) i ryczałt, z terminami płatności.

    health_paid / social_paid to składki faktycznie zapłacone w tym miesiącu (odliczane od
    przychodu). Bez nich przyjmowane są składki należne za poprzedni miesiąc.
    """
    return await _call(
        tools.monthly_obligations,
        year=year,
        month=month,
        health_paid=health_paid,
        social_paid=social_paid,
    )


@mcp.tool(annotations=READ)
async def annual_settlement_preview(year: Year) -> dict[str, Any]:
    """Podgląd rozliczenia rocznego: PIT-28 (podatek, zaliczki, dopłata/nadpłata) i roczna składka zdrowotna."""
    return await _call(tools.annual_settlement_preview, year=year)


@mcp.tool(annotations=READ)
async def month_close_checks(year: Year, month: Month) -> dict[str, Any]:
    """Kontrola kompletności miesiąca: faktury bez pozycji, przeterminowane, niewysłane do KSeF, zakupy i dyżury do sprawdzenia."""
    return await _call(tools.month_close_checks, year=year, month=month)


@mcp.tool(annotations=READ)
async def ksef_overview() -> dict[str, Any]:
    """Stan integracji z KSeF: środowisko, faktury wg statusu wysyłki, ostatnie błędy."""
    return await _call(tools.ksef_overview)


@mcp.tool(annotations=READ)
async def unbilled_duty_shifts(
    year: Year | None = None, month: Month | None = None
) -> dict[str, Any]:
    """Dyżury medyczne jeszcze nierozliczone na fakturze, z wartością wg cennika."""
    return await _call(tools.unbilled_duty_shifts, year=year, month=month)


@mcp.tool(annotations=READ)
async def list_reports(limit: Annotated[int, Field(ge=1, le=20)] = 5) -> dict[str, Any]:
    """Ostatnie raporty agenta (np. zamknięcie miesiąca)."""
    return await _call(tools.list_reports, limit=limit)


# ---------------------------------------------------------------------------
# Zapis — zawsze najpierw podgląd (confirm=false)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=WRITE)
async def save_monthly_settlement(
    year: Year,
    month: Month,
    health_paid: Money = None,
    social_paid: Money = None,
    confirm: Confirm = False,
) -> dict[str, Any]:
    """Zapisuje szkic rozliczenia miesięcznego (do zatwierdzenia). Nie nadpisuje zatwierdzonych."""
    return await _call(
        tools.save_monthly_settlement,
        year=year,
        month=month,
        health_paid=health_paid,
        social_paid=social_paid,
        confirm=confirm,
    )


@mcp.tool(annotations=WRITE)
async def approve_monthly_settlement(
    year: Year, month: Month, confirm: Confirm = False
) -> dict[str, Any]:
    """Zatwierdza szkic rozliczenia miesięcznego."""
    return await _call(
        tools.approve_monthly_settlement, year=year, month=month, confirm=confirm
    )


@mcp.tool(annotations=WRITE)
async def save_annual_settlement(
    year: Year, confirm: Confirm = False
) -> dict[str, Any]:
    """Zapisuje rozliczenie roczne (PIT-28) wyliczone z rozliczeń miesięcznych."""
    return await _call(tools.save_annual_settlement, year=year, confirm=confirm)


@mcp.tool(annotations=WRITE_EXTERNAL)
async def import_from_ksef(
    kind: Annotated[
        Literal["sales", "purchases"],
        Field(description="sales = sprzedaż, purchases = zakupy"),
    ],
    days: Annotated[int, Field(ge=1, le=90, description="Ile dni wstecz")] = 30,
    confirm: Confirm = False,
) -> dict[str, Any]:
    """Pobiera faktury z KSeF do aplikacji (bez duplikatów)."""
    return await _call(tools.import_from_ksef, kind=kind, days=days, confirm=confirm)


@mcp.custom_route("/mcp-health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def build_app():
    """Nowa aplikacja ASGI (menedżer sesji MCP jest jednorazowy — w testach budujemy osobno)."""
    return mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=ALLOWED_HOSTS,
            allowed_origins=[],
        ),
    )


app = build_app()
