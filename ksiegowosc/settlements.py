"""Rozliczenia na danych z bazy: przychody, składki, ryczałt, rozliczenie roczne.

Warstwa łącząca ORM z silnikiem obliczeń (ksiegowosc.tax_engine). Z tych funkcji
korzystają widoki admina, narzędzia asystenta (serwer MCP) i agent zamknięcia miesiąca.
Każda funkcja działa w kontekście jednego użytkownika.
"""

from __future__ import annotations

import calendar as pycalendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from .models import (
    CompanyInfo,
    DutyShift,
    Invoice,
    MonthlySettlement,
    PurchaseInvoice,
    YearlySettlement,
)
from .tax_engine import (
    ZUS_VARIANT_LABELS,
    MissingYearParams,
    annual_health_deadline,
    annual_return_deadline,
    health_contribution,
    lump_sum_deadline,
    lump_sum_tax,
    social_contributions,
    zus_deadline,
)

D = Decimal
ZERO = D("0.00")
KSEF_PURCHASE_REVIEW_MARKER = "Sprawdź kategorię"


class SettlementError(Exception):
    """Błąd, który należy pokazać użytkownikowi (brak danych firmy, nieobsługiwana forma itp.)."""


# ---------------------------------------------------------------------------
# Dane podstawowe
# ---------------------------------------------------------------------------


def company_for(user) -> CompanyInfo:
    try:
        return CompanyInfo.objects.get(user=user)
    except CompanyInfo.DoesNotExist:
        raise SettlementError(
            "Brak danych firmy — uzupełnij „Dane firmy” w panelu."
        ) from None


def month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(
        year, month, pycalendar.monthrange(year, month)[1]
    )


def revenue_date(invoice: Invoice) -> date:
    """Data przychodu na ryczałcie: wystawienie faktury, nie później niż wykonanie usługi."""
    if invoice.sale_date and invoice.sale_date < invoice.issue_date:
        return invoice.sale_date
    return invoice.issue_date


def norm_rate(rate) -> Decimal:
    """14.00 -> 14, 8.50 -> 8.5, 10 -> 10 (bez notacji wykładniczej)."""
    return D(format(D(rate).normalize(), "f"))


@dataclass
class RevenueSummary:
    by_rate: dict  # stawka -> kwota
    invoice_count: int
    by_contractor: dict  # nazwa -> kwota

    @property
    def total(self) -> Decimal:
        return sum(self.by_rate.values(), ZERO)


def revenue_between(
    user, start: date, end: date, default_rate: Decimal
) -> RevenueSummary:
    invoices = (
        Invoice.objects.filter(user=user)
        .filter(Q(issue_date__range=(start, end)) | Q(sale_date__range=(start, end)))
        .select_related("contractor")
        .prefetch_related("items")
    )
    by_rate: dict[Decimal, Decimal] = {}
    by_contractor: dict[str, Decimal] = {}
    count = 0
    for inv in invoices:
        if not (start <= revenue_date(inv) <= end):
            continue
        count += 1
        items = list(inv.items.all())
        if items:
            parts = [(D(i.lump_sum_tax_rate), D(i.total_price)) for i in items]
        else:
            parts = [(default_rate, D(inv.total_amount))]
        for rate, amount in parts:
            rate = norm_rate(rate)
            by_rate[rate] = by_rate.get(rate, ZERO) + amount
            by_contractor[inv.contractor.name] = (
                by_contractor.get(inv.contractor.name, ZERO) + amount
            )
    return RevenueSummary(
        by_rate=by_rate, invoice_count=count, by_contractor=by_contractor
    )


# ---------------------------------------------------------------------------
# Miesiąc po miesiącu
# ---------------------------------------------------------------------------


def _profile(company: CompanyInfo):
    profile = company.contribution_profile()
    if profile.tax_form != "ryczalt_ewidencjonowany":
        raise SettlementError(
            f"Forma opodatkowania „{company.get_income_tax_type_display()}” nie jest jeszcze "
            "obsługiwana przez asystenta — obsługiwany jest ryczałt."
        )
    return profile


def _health_due(year: int, profile, cumulative_base: Decimal) -> dict:
    return health_contribution(year, profile, cumulative_base)


def _previous_december_dues(
    user, company, profile, year: int
) -> tuple[Decimal, Decimal, list[str]]:
    """Składki należne za grudzień roku poprzedniego (zapłacone zwykle w styczniu)."""
    notes = []
    prev = year - 1
    try:
        social = social_contributions(prev, profile)
        rev = revenue_between(
            user, date(prev, 1, 1), date(prev, 12, 31), profile.default_lump_sum_rate
        )
        health = _health_due(
            prev, profile, max(ZERO, rev.total - social.social_total * 12)
        )["skladka"]
        return social.social_total, health, notes
    except MissingYearParams:
        notes.append(
            f"brak parametrów składek za {prev} — przyjęto 0 zł składek zapłaconych w styczniu"
        )
        return ZERO, ZERO, notes


def year_breakdown(
    user, year: int, through_month: int, overrides: dict | None = None
) -> dict:
    """Wylicza miesiące od stycznia do `through_month` z przenoszeniem odliczeń.

    Kwoty zapłacone w danym miesiącu bierze z zapisanego rozliczenia miesięcznego; gdy go
    nie ma, przyjmuje, że w miesiącu zapłacono składki należne za miesiąc poprzedni.
    `overrides` = {miesiąc: {"health_paid": D, "social_paid": D}} nadpisuje te kwoty.
    """
    company = company_for(user)
    profile = _profile(company)
    overrides = overrides or {}
    social = social_contributions(year, profile)
    saved = {s.month: s for s in MonthlySettlement.objects.filter(user=user, year=year)}

    months = []
    cumulative_revenue = ZERO
    cumulative_social_paid = ZERO
    carry = ZERO
    prev_social_due, prev_health_due, notes = _previous_december_dues(
        user, company, profile, year
    )

    for m in range(1, through_month + 1):
        start, end = month_range(year, m)
        revenue = revenue_between(user, start, end, profile.default_lump_sum_rate)
        month_notes = []

        override = overrides.get(m, {})
        record = saved.get(m)
        if "health_paid" in override or "social_paid" in override:
            health_paid = D(override.get("health_paid", prev_health_due))
            social_paid = D(override.get("social_paid", prev_social_due))
            source = "podane"
        elif record is not None:
            health_paid = D(record.health_insurance_paid)
            social_paid = D(record.social_insurance_paid)
            source = f"z zapisanego rozliczenia ({record.get_status_display().lower()})"
        else:
            health_paid, social_paid = prev_health_due, prev_social_due
            source = "założenie: zapłacono składki należne za poprzedni miesiąc"
        month_notes.append(f"składki zapłacone w miesiącu — {source}")

        cumulative_revenue += revenue.total
        cumulative_social_paid += social_paid
        health = _health_due(
            year, profile, max(ZERO, cumulative_revenue - cumulative_social_paid)
        )
        tax = lump_sum_tax(
            revenue.by_rate,
            social_paid=social_paid,
            health_paid=health_paid,
            carried_deductions=carry,
        )
        carry = tax.carry_forward

        months.append(
            {
                "month": m,
                "revenue": revenue,
                "social_due": social,
                "health_due": health,
                "health_paid": health_paid,
                "social_paid": social_paid,
                "tax": tax,
                "saved": record,
                "notes": month_notes,
            }
        )
        prev_social_due, prev_health_due = social.social_total, health["skladka"]

    return {"company": company, "profile": profile, "months": months, "notes": notes}


def monthly_obligations(
    user, year: int, month: int, health_paid=None, social_paid=None
) -> dict:
    overrides = {}
    if health_paid is not None or social_paid is not None:
        overrides[month] = {
            k: D(v)
            for k, v in (("health_paid", health_paid), ("social_paid", social_paid))
            if v is not None
        }
    data = year_breakdown(user, year, month, overrides)
    row = data["months"][-1]
    company, profile = data["company"], data["profile"]
    social, health, tax = row["social_due"], row["health_due"], row["tax"]
    zus_total = social.total + health["skladka"]
    saved = row["saved"]

    return {
        "okres": f"{month:02d}/{year}",
        "profil": {
            "forma_opodatkowania": company.get_income_tax_type_display(),
            "wariant_zus": ZUS_VARIANT_LABELS[profile.zus_variant],
            "domyslna_stawka_ryczaltu": profile.default_lump_sum_rate,
        },
        "przychod": {
            "razem": row["revenue"].total,
            "wg_stawek": {f"{k}%": v for k, v in row["revenue"].by_rate.items()},
            "liczba_faktur": row["revenue"].invoice_count,
            "wg_kontrahentow": row["revenue"].by_contractor,
            "narastajaco_od_poczatku_roku": sum(
                (r["revenue"].total for r in data["months"]), ZERO
            ),
        },
        "zus_za_miesiac": {
            "spoleczne": social.as_dict(),
            "zdrowotna": health,
            "razem_do_zaplaty": zus_total,
            "termin": zus_deadline(year, month),
        },
        "ryczalt_za_miesiac": {
            **tax.as_dict(),
            "skladki_spoleczne_zaplacone_w_miesiacu": row["social_paid"],
            "skladka_zdrowotna_zaplacona_w_miesiacu": row["health_paid"],
            "termin": lump_sum_deadline(year, month),
        },
        "zapisane_rozliczenie": (
            {
                "status": saved.get_status_display(),
                "podatek": saved.income_tax_payable,
                "zdrowotna_zaplacona": saved.health_insurance_paid,
            }
            if saved
            else None
        ),
        "uwagi": data["notes"] + row["notes"],
    }


def annual_settlement(user, year: int) -> dict:
    data = year_breakdown(user, year, 12)
    company, profile, months = data["company"], data["profile"], data["months"]

    revenue_by_rate: dict[Decimal, Decimal] = {}
    for row in months:
        for rate, amount in row["revenue"].by_rate.items():
            revenue_by_rate[rate] = revenue_by_rate.get(rate, ZERO) + amount
    social_paid = sum((r["social_paid"] for r in months), ZERO)
    health_paid = sum((r["health_paid"] for r in months), ZERO)
    annual_tax = lump_sum_tax(
        revenue_by_rate, social_paid=social_paid, health_paid=health_paid
    )

    advances = ZERO
    advance_sources = set()
    for row in months:
        if row["saved"] is not None:
            advances += D(row["saved"].income_tax_payable)
            advance_sources.add("zapisane rozliczenia")
        else:
            advances += row["tax"].tax
            advance_sources.add("wyliczenie")

    # Roczne rozliczenie zdrowotnej: należna = 12 × składka z progu dla przychodu rocznego
    active_months = 12
    if company.business_start_date and company.business_start_date.year == year:
        active_months = 13 - company.business_start_date.month
    revenue_total = sum(revenue_by_rate.values(), ZERO)
    annual_health_base = max(ZERO, revenue_total - social_paid)
    health_tier = _health_due(year, profile, annual_health_base)
    health_due_year = health_tier["skladka"] * active_months
    health_monthly_sum = sum(
        (r["health_due"]["skladka"] for r in months[13 - active_months - 1 :]), ZERO
    )

    drafts = [
        r["month"]
        for r in months
        if r["saved"] is not None and r["saved"].status == "draft"
    ]
    missing = [r["month"] for r in months if r["saved"] is None]
    notes = list(data["notes"])
    if drafts:
        notes.append(f"miesiące ze szkicem (niezatwierdzone): {drafts}")
    if missing:
        notes.append(
            f"miesiące bez zapisanego rozliczenia (przyjęto założenia): {missing}"
        )

    return {
        "rok": year,
        "przychod": {
            "razem": revenue_total,
            "wg_stawek": {f"{k}%": v for k, v in revenue_by_rate.items()},
        },
        "pit28": {
            **annual_tax.as_dict(),
            "skladki_spoleczne_odliczone": social_paid,
            "skladka_zdrowotna_zaplacona": health_paid,
            "polowa_zdrowotnej_odliczona": (health_paid / 2).quantize(D("0.01")),
            "zaplacone_zaliczki": advances,
            "zrodlo_zaliczek": ", ".join(sorted(advance_sources)),
            "do_zaplaty" if annual_tax.tax >= advances else "nadplata": abs(
                annual_tax.tax - advances
            ),
            "termin": annual_return_deadline(year),
        },
        "zdrowotna_roczna": {
            "podstawa_przychod_minus_spoleczne": annual_health_base,
            "skladka_miesieczna_wg_progu_rocznego": health_tier["skladka"],
            "miesiace_dzialalnosci": active_months,
            "nalezna_za_rok": health_due_year,
            "nalezna_miesiecznie_suma": health_monthly_sum,
            "doplata" if health_due_year >= health_monthly_sum else "nadplata": abs(
                health_due_year - health_monthly_sum
            ),
            "termin": annual_health_deadline(year),
            "uwaga": "porównanie z sumą składek należnych miesięcznie (zakłada terminowe opłacanie)",
        },
        "uwagi": notes,
    }


# ---------------------------------------------------------------------------
# Kontrola kompletności (dla agenta zamknięcia miesiąca)
# ---------------------------------------------------------------------------


def completeness_checks(user, year: int, month: int) -> list[dict]:
    start, end = month_range(year, month)
    today = timezone.localdate()
    company = company_for(user)
    issues = []

    month_invoices = Invoice.objects.filter(user=user, issue_date__range=(start, end))
    no_items = month_invoices.filter(items__isnull=True).count()
    if no_items:
        issues.append(
            {
                "poziom": "uwaga",
                "opis": f"Faktury bez pozycji w {month:02d}/{year}: {no_items}",
            }
        )

    overdue = [
        inv
        for inv in Invoice.objects.filter(
            user=user, payment_date__lt=today
        ).select_related("contractor")
        if inv.payment_status == "overdue"
    ]
    if overdue:
        total = sum((inv.balance_due for inv in overdue), ZERO)
        issues.append(
            {
                "poziom": "uwaga",
                "opis": f"Przeterminowane nieopłacone faktury: {len(overdue)} na {total} zł",
                "faktury": [
                    f"{inv.invoice_number} ({inv.contractor.name}, {inv.balance_due} zł)"
                    for inv in overdue[:10]
                ],
            }
        )

    if company.ksef_environment == "production":
        unsent = month_invoices.exclude(ksef_status="success")
        if unsent.exists():
            issues.append(
                {
                    "poziom": "wazne",
                    "opis": f"Faktury z {month:02d}/{year} niewysłane do KSeF: {unsent.count()}",
                    "faktury": list(
                        unsent.values_list("invoice_number", flat=True)[:10]
                    ),
                }
            )

    to_review = PurchaseInvoice.objects.filter(
        user=user, notes__icontains=KSEF_PURCHASE_REVIEW_MARKER
    ).count()
    if to_review:
        issues.append(
            {
                "poziom": "uwaga",
                "opis": f"Zakupy z KSeF do sprawdzenia (kategoria, odliczenia): {to_review}",
            }
        )

    unbilled = DutyShift.objects.filter(
        user=user, invoice__isnull=True, date__range=(start, end)
    ).count()
    if unbilled:
        issues.append(
            {
                "poziom": "uwaga",
                "opis": f"Nierozliczone dyżury z {month:02d}/{year}: {unbilled}",
            }
        )

    next_year = year + 1 if month == 12 else year
    try:
        from .tax_engine import get_year_params

        get_year_params(next_year)
    except MissingYearParams:
        issues.append(
            {
                "poziom": "wazne",
                "opis": f"Brak parametrów składek na {next_year} — trzeba je dopisać.",
            }
        )
    return issues


# ---------------------------------------------------------------------------
# Zapis rozliczeń
# ---------------------------------------------------------------------------


def to_jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    return value


def save_monthly_settlement(
    user,
    year: int,
    month: int,
    health_paid=None,
    social_paid=None,
    labor_fund_paid=None,
    status: str = "draft",
    overwrite_approved: bool = False,
) -> tuple[MonthlySettlement, bool, dict]:
    """Zapisuje (lub aktualizuje) rozliczenie miesięczne wyliczone przez silnik.

    Zatwierdzonego rozliczenia nie nadpisuje, chyba że `overwrite_approved=True`.
    Zwraca (rozliczenie, czy_utworzono, wyliczenie).
    """
    existing = MonthlySettlement.objects.filter(
        user=user, year=year, month=month
    ).first()
    if existing and existing.status == "approved" and not overwrite_approved:
        raise SettlementError(
            f"Rozliczenie {month:02d}/{year} jest już zatwierdzone — nie nadpisuję go."
        )
    result = monthly_obligations(
        user, year, month, health_paid=health_paid, social_paid=social_paid
    )
    lump = result["ryczalt_za_miesiac"]
    if labor_fund_paid is None:
        labor_fund_paid = result["zus_za_miesiac"]["spoleczne"]["fundusz_pracy"]

    settlement, created = MonthlySettlement.objects.update_or_create(
        user=user,
        year=year,
        month=month,
        defaults={
            "total_revenue": result["przychod"]["razem"],
            "health_insurance_paid": lump["skladka_zdrowotna_zaplacona_w_miesiacu"],
            "social_insurance_paid": lump["skladki_spoleczne_zaplacone_w_miesiacu"],
            "labor_fund_paid": D(labor_fund_paid),
            "income_tax_payable": lump["podatek"],
            "status": status,
            "details": to_jsonable(result),
            "approved_at": timezone.now() if status == "approved" else None,
        },
    )
    return settlement, created, result


def save_annual_settlement(
    user, year: int, notes: str = ""
) -> tuple[YearlySettlement, bool, dict]:
    result = annual_settlement(user, year)
    pit = result["pit28"]
    company = company_for(user)
    settlement, created = YearlySettlement.objects.update_or_create(
        user=user,
        year=year,
        defaults={
            "total_yearly_revenue": result["przychod"]["razem"],
            "total_social_insurance_paid": pit["skladki_spoleczne_odliczone"],
            "total_health_insurance_paid": pit["skladka_zdrowotna_zaplacona"],
            "total_monthly_tax_paid": pit["zaplacone_zaliczki"],
            "calculated_yearly_tax": pit["podatek"],
            "tax_difference": pit["podatek"] - pit["zaplacone_zaliczki"],
            "tax_rate_used": D(company.lump_sum_rate or "14"),
            "notes": notes,
        },
    )
    return settlement, created, result
