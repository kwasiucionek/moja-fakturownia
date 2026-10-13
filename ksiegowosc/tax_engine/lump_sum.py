"""Ryczałt od przychodów ewidencjonowanych — zaliczki miesięczne i rozliczenie roczne.

Zasady:
- przychód pomniejsza się o zapłacone w danym miesiącu składki społeczne oraz o 50%
  zapłaconej składki zdrowotnej (art. 11 ust. 1 i 1c ustawy o zryczałtowanym podatku),
- odliczenia nieodliczone w danym miesiącu przechodzą na kolejne miesiące tego roku,
- przy kilku stawkach odliczenia są przypisywane najpierw do przychodu z najwyższą
  stawką (wybór korzystny dla podatnika, ustawa pozostawia go podatnikowi),
- podstawa opodatkowania i podatek zaokrąglane do pełnych złotych (art. 63 Ordynacji).
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

D = Decimal
ZERO = D("0.00")


def full_zloty(value: Decimal) -> Decimal:
    return D(value).quantize(D("1"), rounding=ROUND_HALF_UP)


@dataclass
class LumpSumResult:
    tax: Decimal
    bases: dict  # stawka (%) -> podstawa po odliczeniach (pełne zł)
    revenue: dict  # stawka (%) -> przychód
    deductions_available: Decimal
    deductions_used: Decimal
    carry_forward: Decimal
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "przychod_wg_stawek": {f"{k}%": v for k, v in self.revenue.items()},
            "podstawa_wg_stawek": {f"{k}%": v for k, v in self.bases.items()},
            "odliczenia_dostepne": self.deductions_available,
            "odliczenia_wykorzystane": self.deductions_used,
            "odliczenia_na_kolejne_miesiace": self.carry_forward,
            "podatek": self.tax,
            "uwagi": list(self.notes),
        }


def lump_sum_tax(
    revenue_by_rate: dict[Decimal, Decimal],
    social_paid: Decimal = ZERO,
    health_paid: Decimal = ZERO,
    carried_deductions: Decimal = ZERO,
) -> LumpSumResult:
    """Podatek ryczałtowy od przychodów pogrupowanych wg stawek (w procentach).

    Działa tak samo dla miesiąca (zaliczka) i dla roku (PIT-28) — dla roku podaje się
    sumy przychodów i zapłaconych składek z całego roku.
    """
    revenue = {
        D(rate): D(amount) for rate, amount in revenue_by_rate.items() if D(amount) != 0
    }
    notes = []

    deductions = D(social_paid) + D(health_paid) * D("0.5") + D(carried_deductions)
    # Ujemny przychód (np. korekty in minus) działa jak dodatkowe odliczenie
    for rate, amount in list(revenue.items()):
        if amount < 0:
            deductions += -amount
            revenue[rate] = ZERO
            notes.append(
                f"ujemny przychód przy stawce {rate}% (korekty) potraktowany jak odliczenie"
            )

    remaining = deductions
    bases = {}
    tax = ZERO
    for rate in sorted(revenue, reverse=True):
        amount = revenue[rate]
        used = min(amount, remaining)
        remaining -= used
        base = full_zloty(amount - used)
        bases[rate] = base
        tax += base * rate / D("100")

    return LumpSumResult(
        tax=full_zloty(tax),
        bases=bases,
        revenue=revenue,
        deductions_available=deductions.quantize(D("0.01")),
        deductions_used=(deductions - remaining).quantize(D("0.01")),
        carry_forward=remaining.quantize(D("0.01")),
        notes=notes,
    )
