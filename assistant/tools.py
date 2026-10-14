"""Narzędzia asystenta — wspólne dla serwera MCP i agentów.

Każde narzędzie działa w imieniu jednego użytkownika i widzi wyłącznie jego dane.
Narzędzia zapisujące:
- wymagają tokena z uprawnieniem zapisu,
- bez `confirm=True` zwracają tylko podgląd tego, co zostałoby zapisane,
- nie nadpisują zatwierdzonych rozliczeń.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count
from django.utils import timezone

from ksiegowosc import settlements
from ksiegowosc.models import (
    BusinessSuspension,
    DutyRate,
    DutyShift,
    Invoice,
    MonthlySettlement,
)
from ksiegowosc.settlements import SettlementError, to_jsonable

from .models import AssistantReport

D = Decimal


class ToolInputError(Exception):
    """Błąd do pokazania modelowi (zła wartość, brak uprawnień, brak danych)."""


def _require_write(scopes) -> None:
    if "write" not in scopes:
        raise ToolInputError(
            "Ten token ma tylko uprawnienie odczytu — zapis jest niedostępny."
        )


def _check_period(year: int, month: int | None = None) -> None:
    if not 2000 <= year <= 2100:
        raise ToolInputError(f"Nieprawidłowy rok: {year}")
    if month is not None and not 1 <= month <= 12:
        raise ToolInputError(f"Nieprawidłowy miesiąc: {month}")


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ToolInputError(
            f"{field}: oczekiwano daty w formacie RRRR-MM-DD, otrzymano {value!r}"
        ) from None


def _wrap(fn):
    """Zamienia błędy domenowe na ToolInputError i wynik na JSON-owalny słownik."""

    def inner(*args, **kwargs):
        try:
            return to_jsonable(fn(*args, **kwargs))
        except (SettlementError, ValueError, NotImplementedError, LookupError) as exc:
            raise ToolInputError(str(exc)) from exc

    inner.__name__ = fn.__name__
    inner.__doc__ = fn.__doc__
    return inner


# ---------------------------------------------------------------------------
# Odczyt
# ---------------------------------------------------------------------------


@_wrap
def company_profile(user, scopes=()) -> dict:
    c = settlements.company_for(user)
    profile = c.contribution_profile()
    return {
        "firma": c.company_name,
        "nip": c.tax_id,
        "forma_opodatkowania": c.get_income_tax_type_display(),
        "domyslna_stawka_ryczaltu": c.lump_sum_rate,
        "wariant_zus": settlements.ZUS_VARIANT_LABELS[profile.zus_variant],
        "dobrowolne_chorobowe": c.zus_sickness_insurance,
        "platnik_vat": c.vat_payer,
        "srodowisko_ksef": c.ksef_environment,
        "token_ksef_ustawiony": bool(c.ksef_token),
        "data_rozpoczecia_dzialalnosci": c.business_start_date,
        "zawieszenia_dzialalnosci": [
            {"od": z.date_from, "do": z.date_to, "uwagi": z.notes}
            for z in BusinessSuspension.objects.filter(user=user)
        ],
        "uprawnienia_tokena": list(scopes),
    }


@_wrap
def revenue_summary(user, year: int, month: int | None = None, scopes=()) -> dict:
    _check_period(year, month)
    company = settlements.company_for(user)
    if month:
        start, end = settlements.month_range(year, month)
    else:
        start, end = date(year, 1, 1), date(year, 12, 31)
    rev = settlements.revenue_between(
        user, start, end, D(company.lump_sum_rate or "14")
    )
    return {
        "okres": f"{month:02d}/{year}" if month else str(year),
        "przychod_razem": rev.total,
        "wg_stawek_ryczaltu": {f"{k}%": v for k, v in rev.by_rate.items()},
        "wg_kontrahentow": dict(
            sorted(rev.by_contractor.items(), key=lambda kv: -kv[1])
        ),
        "liczba_faktur": rev.invoice_count,
        "uwaga": "data przychodu = data wystawienia faktury, nie później niż data wykonania usługi",
    }


def _invoice_row(inv: Invoice) -> dict:
    return {
        "numer": inv.invoice_number,
        "kontrahent": inv.contractor.name,
        "data_wystawienia": inv.issue_date,
        "data_sprzedazy": inv.sale_date,
        "termin_platnosci": inv.payment_date,
        "kwota": inv.total_amount,
        "do_zaplaty": inv.balance_due,
        "status_platnosci": inv.payment_status_display,
        "status_ksef": inv.get_ksef_status_display(),
        "korekta": inv.is_correction,
    }


@_wrap
def list_invoices(
    user,
    date_from: str,
    date_to: str,
    contractor: str | None = None,
    payment_status: str | None = None,
    limit: int = 50,
    scopes=(),
) -> dict:
    start, end = _parse_date(date_from, "date_from"), _parse_date(date_to, "date_to")
    qs = Invoice.objects.filter(
        user=user, issue_date__range=(start, end)
    ).select_related("contractor")
    if contractor:
        qs = qs.filter(contractor__name__icontains=contractor)
    rows = [_invoice_row(inv) for inv in qs.order_by("issue_date")]
    if payment_status:
        rows = [
            r
            for r in rows
            if r["status_platnosci"].lower().startswith(payment_status.lower()[:5])
        ]
    limit = max(1, min(limit, 200))
    return {"liczba": len(rows), "faktury": rows[:limit], "obcieto": len(rows) > limit}


@_wrap
def unpaid_invoices(user, overdue_only: bool = False, scopes=()) -> dict:
    rows = []
    for inv in (
        Invoice.objects.filter(user=user)
        .select_related("contractor")
        .order_by("payment_date")
    ):
        status = inv.payment_status
        if status == "paid" or (overdue_only and status != "overdue"):
            continue
        rows.append(_invoice_row(inv))
    total = sum((r["do_zaplaty"] for r in rows), D("0"))
    return {"liczba": len(rows), "do_zaplaty_razem": total, "faktury": rows}


@_wrap
def monthly_obligations(
    user, year: int, month: int, health_paid=None, social_paid=None, scopes=()
) -> dict:
    _check_period(year, month)
    return settlements.monthly_obligations(
        user, year, month, health_paid=health_paid, social_paid=social_paid
    )


@_wrap
def annual_settlement_preview(user, year: int, scopes=()) -> dict:
    _check_period(year)
    return settlements.annual_settlement(user, year)


@_wrap
def month_close_checks(user, year: int, month: int, scopes=()) -> dict:
    _check_period(year, month)
    issues = settlements.completeness_checks(user, year, month)
    return {"okres": f"{month:02d}/{year}", "liczba_uwag": len(issues), "uwagi": issues}


@_wrap
def ksef_overview(user, scopes=()) -> dict:
    company = settlements.company_for(user)
    by_status = {
        row["ksef_status"]: row["n"]
        for row in Invoice.objects.filter(user=user)
        .values("ksef_status")
        .annotate(n=Count("id"))
    }
    labels = dict(Invoice._meta.get_field("ksef_status").choices)
    errors = Invoice.objects.filter(user=user, ksef_status="error").order_by(
        "-issue_date"
    )[:10]
    return {
        "srodowisko": company.ksef_environment,
        "token_ustawiony": bool(company.ksef_token),
        "faktury_wg_statusu": {labels.get(k, k): v for k, v in by_status.items()},
        "ostatnie_bledy": [
            {"numer": i.invoice_number, "opis": i.ksef_processing_description}
            for i in errors
        ],
    }


@_wrap
def unbilled_duty_shifts(
    user, year: int | None = None, month: int | None = None, scopes=()
) -> dict:
    qs = DutyShift.objects.filter(user=user, invoice__isnull=True).select_related(
        "contractor"
    )
    if year:
        qs = qs.filter(date__year=year)
    if month:
        qs = qs.filter(date__month=month)
    rows, missing_rate = [], 0
    by_contractor: dict[str, Decimal] = {}
    for s in qs.order_by("date", "start_time"):
        value = s.value
        if value is None:
            missing_rate += 1
        else:
            by_contractor[s.contractor.name] = (
                by_contractor.get(s.contractor.name, D("0")) + value
            )
        rows.append(
            {
                "data": s.date,
                "od": s.start_time.strftime("%H:%M"),
                "do": s.end_time.strftime("%H:%M"),
                "godziny": s.hours,
                "rodzaj": s.get_shift_type_display(),
                "weekend_lub_swieto": s.is_weekend_or_holiday,
                "kontrahent": s.contractor.name,
                "wartosc": value,
            }
        )
    notes = []
    if missing_rate:
        notes.append(
            f"dyżury bez cennika na ich dzień: {missing_rate} — uzupełnij „Stawki za dyżury”"
        )
    return {
        "liczba": len(rows),
        "godziny_razem": sum((r["godziny"] for r in rows), D("0")),
        "wartosc_wg_kontrahentow": by_contractor,
        "dyzury": rows,
        "uwagi": notes,
        "cenniki": DutyRate.objects.filter(user=user).count(),
    }


@_wrap
def list_reports(user, limit: int = 5, scopes=()) -> dict:
    reports = AssistantReport.objects.filter(user=user)[: max(1, min(limit, 20))]
    return {
        "raporty": [
            {
                "tytul": r.title,
                "okres": r.period,
                "utworzono": timezone.localtime(r.created_at).isoformat(
                    timespec="minutes"
                ),
                "wymaga_uwagi": r.has_issues,
                "tresc": r.content,
            }
            for r in reports
        ]
    }


# ---------------------------------------------------------------------------
# Zapis (wymaga uprawnienia zapisu i potwierdzenia)
# ---------------------------------------------------------------------------


@_wrap
def save_monthly_settlement(
    user,
    year: int,
    month: int,
    health_paid=None,
    social_paid=None,
    confirm: bool = False,
    scopes=(),
) -> dict:
    _require_write(scopes)
    _check_period(year, month)
    preview = settlements.monthly_obligations(
        user, year, month, health_paid=health_paid, social_paid=social_paid
    )
    existing = MonthlySettlement.objects.filter(
        user=user, year=year, month=month
    ).first()
    if existing and existing.status == "approved":
        raise ToolInputError(
            f"Rozliczenie {month:02d}/{year} jest już zatwierdzone — nie można go nadpisać."
        )
    summary = {
        "okres": preview["okres"],
        "przychod": preview["przychod"]["razem"],
        "skladka_zdrowotna_zaplacona_w_miesiacu": preview["ryczalt_za_miesiac"][
            "skladka_zdrowotna_zaplacona_w_miesiacu"
        ],
        "skladki_spoleczne_zaplacone_w_miesiacu": preview["ryczalt_za_miesiac"][
            "skladki_spoleczne_zaplacone_w_miesiacu"
        ],
        "ryczalt_do_zaplaty": preview["ryczalt_za_miesiac"]["podatek"],
        "termin_ryczaltu": preview["ryczalt_za_miesiac"]["termin"],
        "zus_do_zaplaty": preview["zus_za_miesiac"]["razem_do_zaplaty"],
        "termin_zus": preview["zus_za_miesiac"]["termin"],
        "nadpisze_szkic": bool(existing),
        "uwagi": preview["uwagi"],
    }
    if not confirm:
        return {
            "zapisano": False,
            "podglad": summary,
            "instrukcja": "To jest podgląd. Pokaż go użytkownikowi i wywołaj ponownie z confirm=true po jego zgodzie.",
        }
    settlement, created, _ = settlements.save_monthly_settlement(
        user,
        year,
        month,
        health_paid=health_paid,
        social_paid=social_paid,
        status="draft",
    )
    return {
        "zapisano": True,
        "utworzono": created,
        "status": settlement.get_status_display(),
        "podsumowanie": summary,
        "nastepny_krok": "Szkic czeka na zatwierdzenie (approve_monthly_settlement lub w panelu).",
    }


@_wrap
def approve_monthly_settlement(
    user, year: int, month: int, confirm: bool = False, scopes=()
) -> dict:
    _require_write(scopes)
    _check_period(year, month)
    s = MonthlySettlement.objects.filter(user=user, year=year, month=month).first()
    if s is None:
        raise ToolInputError(
            f"Brak rozliczenia {month:02d}/{year} — najpierw je zapisz."
        )
    if s.status == "approved":
        return {"zatwierdzono": False, "info": "Rozliczenie jest już zatwierdzone."}
    info = {
        "okres": f"{month:02d}/{year}",
        "przychod": s.total_revenue,
        "ryczalt": s.income_tax_payable,
        "zdrowotna_zaplacona": s.health_insurance_paid,
    }
    if not confirm:
        return {
            "zatwierdzono": False,
            "podglad": info,
            "instrukcja": "Wywołaj z confirm=true po zgodzie użytkownika.",
        }
    s.status = "approved"
    s.approved_at = timezone.now()
    s.save(update_fields=["status", "approved_at"])
    return {"zatwierdzono": True, **info}


@_wrap
def save_annual_settlement(user, year: int, confirm: bool = False, scopes=()) -> dict:
    _require_write(scopes)
    _check_period(year)
    preview = settlements.annual_settlement(user, year)
    if not confirm:
        return {
            "zapisano": False,
            "podglad": {
                "pit28": preview["pit28"],
                "zdrowotna_roczna": preview["zdrowotna_roczna"],
            },
            "uwagi": preview["uwagi"],
            "instrukcja": "To jest podgląd. Wywołaj z confirm=true po zgodzie użytkownika.",
        }
    settlement, created, _ = settlements.save_annual_settlement(
        user, year, notes="Zapisane przez asystenta"
    )
    return {
        "zapisano": True,
        "utworzono": created,
        "podatek": settlement.calculated_yearly_tax,
    }


@_wrap
def import_from_ksef(
    user,
    kind: str,
    days: int = 30,
    date_from: str | None = None,
    date_to: str | None = None,
    confirm: bool = False,
    scopes=(),
) -> dict:
    _require_write(scopes)
    if kind not in ("sales", "purchases"):
        raise ToolInputError(
            "kind: dozwolone wartości to 'sales' (sprzedaż) lub 'purchases' (zakupy)."
        )
    company = settlements.company_for(user)
    if not company.ksef_token:
        raise ToolInputError("Brak tokena KSeF w danych firmy.")
    start = _parse_date(date_from, "date_from") if date_from else None
    end = _parse_date(date_to, "date_to") if date_to else None
    if end and not start:
        raise ToolInputError("date_to wymaga date_from.")
    days = max(1, min(int(days), 730))
    if start:
        period = f"{start} – {end or timezone.localdate()}"
    else:
        period = (
            f"ostatnie {days} dni (od {timezone.localdate() - timedelta(days=days)})"
        )
    plan = {
        "rodzaj": "faktury sprzedaży" if kind == "sales" else "faktury zakupu",
        "okres": period,
        "srodowisko": company.ksef_environment,
        "zachowanie": "istniejące faktury nie są duplikowane; okres pobierany miesiąc po miesiącu",
    }
    if not confirm:
        return {
            "zaimportowano": False,
            "plan": plan,
            "instrukcja": "Wywołaj z confirm=true po zgodzie użytkownika.",
        }

    from ksef.ksef2_import import (
        import_purchase_invoices_from_ksef,
        import_sales_invoices_from_ksef,
    )

    kwargs = {"days": days, "date_from": start, "date_to": end}
    if kind == "sales":
        r = import_sales_invoices_from_ksef(company, **kwargs)
        return {
            "zaimportowano": True,
            "utworzono": r.created,
            "zsynchronizowano": r.synced,
            "bledy": r.errors,
        }
    r = import_purchase_invoices_from_ksef(company, **kwargs)
    return {
        "zaimportowano": True,
        "utworzono": r.created,
        "pominieto_istniejace": r.skipped_existing,
        "bledy": r.errors,
        "uwaga": "nowe zakupy mają kategorię domyślną i wymagają sprawdzenia odliczeń",
    }
