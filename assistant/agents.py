"""Agenci wykonujący czynności cykliczne. Każdy wynik to szkic + raport do akceptacji."""

from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail

from ksiegowosc import settlements
from ksiegowosc.models import MonthlySettlement

from .models import AssistantReport

logger = logging.getLogger(__name__)

MONTHS_PL = [
    "",
    "styczeń",
    "luty",
    "marzec",
    "kwiecień",
    "maj",
    "czerwiec",
    "lipiec",
    "sierpień",
    "wrzesień",
    "październik",
    "listopad",
    "grudzień",
]


def zl(value) -> str:
    value = Decimal(value).quantize(Decimal("0.01"))
    return f"{value:,.2f} zł".replace(",", " ").replace(".", ",")


def _report_markdown(
    year: int, month: int, obligations: dict, issues: list[dict], draft_info: str
) -> str:
    zus = obligations["zus_za_miesiac"]
    lump = obligations["ryczalt_za_miesiac"]
    rev = obligations["przychod"]
    social = zus["spoleczne"]
    lines = [
        f"## Zamknięcie miesiąca: {MONTHS_PL[month]} {year}",
        "",
        "### Do zapłaty",
        f"- **ZUS razem: {zl(zus['razem_do_zaplaty'])}** — termin {zus['termin']:%d.%m.%Y}",
        f"  - składka zdrowotna: {zl(zus['zdrowotna']['skladka'])} "
        f"(przychód narastająco {zl(zus['zdrowotna']['przychod_narastajaco'])})",
    ]
    if social["razem"]:
        lines.append(f"  - składki społeczne i FP: {zl(social['razem'])}")
    lines += [
        f"- **Ryczałt: {zl(lump['podatek'])}** — termin {lump['termin']:%d.%m.%Y}",
        "",
        "### Przychód",
        f"- {zl(rev['razem'])} z {rev['liczba_faktur']} faktur; od początku roku {zl(rev['narastajaco_od_poczatku_roku'])}",
    ]
    for rate, amount in rev["wg_stawek"].items():
        lines.append(f"  - stawka {rate}: {zl(amount)}")
    lines += [
        "",
        "### Odliczenia w ryczałcie",
        f"- składka zdrowotna zapłacona w miesiącu: {zl(lump['skladka_zdrowotna_zaplacona_w_miesiacu'])} (odliczono 50%)",
        f"- składki społeczne zapłacone w miesiącu: {zl(lump['skladki_spoleczne_zaplacone_w_miesiacu'])}",
    ]
    if lump["odliczenia_na_kolejne_miesiace"]:
        lines.append(
            f"- przechodzi na kolejne miesiące: {zl(lump['odliczenia_na_kolejne_miesiace'])}"
        )
    lines += ["", "### Do sprawdzenia"]
    if issues:
        for issue in issues:
            marker = "⚠️" if issue["poziom"] == "wazne" else "•"
            lines.append(f"- {marker} {issue['opis']}")
            for item in issue.get("faktury", [])[:5]:
                lines.append(f"  - {item}")
    else:
        lines.append("- brak uwag")
    if obligations["uwagi"]:
        lines += ["", "### Założenia"] + [f"- {n}" for n in obligations["uwagi"]]
    lines += ["", f"_{draft_info}_"]
    return "\n".join(lines)


def close_month(
    user, year: int, month: int, save_draft: bool = True
) -> AssistantReport:
    """Liczy należności za miesiąc, sprawdza kompletność, zapisuje szkic i raport."""
    obligations = settlements.monthly_obligations(user, year, month)
    issues = settlements.completeness_checks(user, year, month)

    existing = MonthlySettlement.objects.filter(
        user=user, year=year, month=month
    ).first()
    if existing and existing.status == "approved":
        draft_info = (
            "Rozliczenie tego miesiąca jest już zatwierdzone — nie zmieniałem go."
        )
    elif save_draft:
        settlements.save_monthly_settlement(user, year, month, status="draft")
        draft_info = "Zapisałem szkic rozliczenia miesięcznego — zatwierdź go w panelu po sprawdzeniu kwot zapłaconych składek."
    else:
        draft_info = "Tryb podglądu — nie zapisano szkicu."

    period = f"{year}-{month:02d}"
    report, _ = AssistantReport.objects.update_or_create(
        user=user,
        kind="month_close",
        period=period,
        defaults={
            "title": f"Zamknięcie miesiąca {month:02d}/{year}: ZUS {zl(obligations['zus_za_miesiac']['razem_do_zaplaty'])}, "
            f"ryczałt {zl(obligations['ryczalt_za_miesiac']['podatek'])}",
            "content": _report_markdown(year, month, obligations, issues, draft_info),
            "data": settlements.to_jsonable(
                {"naleznosci": obligations, "uwagi": issues}
            ),
            "has_issues": bool(issues),
            "read_at": None,
        },
    )
    _notify(user, report)
    return report


def _notify(user, report: AssistantReport) -> None:
    if not getattr(settings, "ASSISTANT_NOTIFY_EMAIL", False) or not user.email:
        return
    try:
        send_mail(report.title, report.content, None, [user.email], fail_silently=False)
    except Exception:  # powiadomienie nie może zablokować raportu
        logger.exception("Nie udało się wysłać raportu %s e-mailem", report.pk)
