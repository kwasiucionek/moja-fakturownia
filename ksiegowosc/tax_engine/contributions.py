"""Składki ZUS przedsiębiorcy: społeczne i zdrowotna.

Wszystkie kwoty w Decimal, zaokrąglane do grosza (ROUND_HALF_UP) na poziomie
pojedynczej składki — tak jak w deklaracji ZUS DRA.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from .params import YearParams, get_year_params

D = Decimal
ZERO = D("0.00")

ZusVariant = Literal[
    "full", "preferential", "small_zus_plus", "start_relief", "health_only"
]
TaxForm = Literal["ryczalt_ewidencjonowany", "skala_podatkowa", "podatek_liniowy"]

ZUS_VARIANT_LABELS = {
    "full": "pełne składki (duży ZUS)",
    "preferential": "preferencyjne składki (30% płacy minimalnej)",
    "small_zus_plus": "Mały ZUS Plus",
    "start_relief": "ulga na start (bez składek społecznych)",
    "health_only": "tylko składka zdrowotna",
}


class UnsupportedTaxForm(NotImplementedError):
    pass


def money(value: Decimal) -> Decimal:
    return D(value).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def pct(base: Decimal, rate_percent: Decimal) -> Decimal:
    return money(base * rate_percent / D("100"))


@dataclass(frozen=True)
class ContributionProfile:
    """Ustawienia przedsiębiorcy istotne dla składek i podatku."""

    tax_form: TaxForm = "ryczalt_ewidencjonowany"
    zus_variant: ZusVariant = "full"
    sickness_insurance: bool = False
    small_zus_plus_base: Decimal | None = None
    default_lump_sum_rate: Decimal = D("14")


@dataclass
class SocialContributions:
    base: Decimal
    pension: Decimal = ZERO
    disability: Decimal = ZERO
    sickness: Decimal = ZERO
    accident: Decimal = ZERO
    labor_fund: Decimal = ZERO
    notes: list[str] = field(default_factory=list)

    @property
    def social_total(self) -> Decimal:
        """Składki na ubezpieczenia społeczne (odliczane od przychodu)."""
        return self.pension + self.disability + self.sickness + self.accident

    @property
    def total(self) -> Decimal:
        """Razem do zapłaty: społeczne + Fundusz Pracy/Solidarnościowy."""
        return self.social_total + self.labor_fund

    def as_dict(self) -> dict:
        return {
            "podstawa": self.base,
            "emerytalna": self.pension,
            "rentowa": self.disability,
            "chorobowa": self.sickness,
            "wypadkowa": self.accident,
            "fundusz_pracy": self.labor_fund,
            "spoleczne_razem": self.social_total,
            "razem": self.total,
            "uwagi": list(self.notes),
        }


def social_contributions(
    year: int,
    profile: ContributionProfile,
    active_days: int | None = None,
    days_in_month: int | None = None,
) -> SocialContributions:
    """Miesięczne składki społeczne dla wariantu z profilu.

    Przy zawieszeniu działalności przez część miesiąca (`active_days` < `days_in_month`)
    podstawę zmniejsza się proporcjonalnie do liczby dni prowadzenia działalności;
    przy zawieszeniu przez cały miesiąc składki nie są należne.
    """
    params = get_year_params(year)
    variant = profile.zus_variant
    partial = (
        active_days is not None
        and days_in_month is not None
        and active_days < days_in_month
    )
    if partial and active_days <= 0:
        return SocialContributions(
            base=ZERO, notes=["zawieszenie działalności przez cały miesiąc"]
        )

    if variant in ("health_only", "start_relief"):
        return SocialContributions(base=ZERO, notes=[ZUS_VARIANT_LABELS[variant]])

    if variant == "preferential":
        base = params.preferential_social_base
    elif variant == "small_zus_plus":
        if profile.small_zus_plus_base is None:
            raise ValueError(
                "Mały ZUS Plus wymaga podstawy wymiaru wyliczonej z dochodu za poprzedni rok "
                "(pole „Podstawa Małego ZUS Plus” w danych firmy)."
            )
        # Podstawa MZP mieści się między 30% płacy minimalnej a 60% prognozowanego wynagrodzenia
        base = min(
            max(money(profile.small_zus_plus_base), params.preferential_social_base),
            params.full_social_base,
        )
    else:
        base = params.full_social_base

    full_month_base = base
    notes = [ZUS_VARIANT_LABELS[variant]]
    if partial:
        base = money(base * active_days / days_in_month)
        notes.append(
            f"podstawa proporcjonalna do dni działalności: {active_days}/{days_in_month}"
        )

    result = SocialContributions(
        base=base,
        pension=pct(base, params.pension_rate),
        disability=pct(base, params.disability_rate),
        accident=pct(base, params.accident_rate),
        notes=notes,
    )
    if profile.sickness_insurance:
        result.sickness = pct(base, params.sickness_rate)
    # Fundusz Pracy nie jest należny, gdy podstawa jest niższa od płacy minimalnej
    if full_month_base >= params.minimum_wage:
        result.labor_fund = pct(base, params.labor_fund_rate)
    else:
        result.notes.append("bez Funduszu Pracy (podstawa niższa niż płaca minimalna)")
    return result


def lump_sum_health_tier(
    params: YearParams, annual_revenue: Decimal
) -> tuple[Decimal, Decimal]:
    """Zwraca (mnożnik, podstawa) składki zdrowotnej ryczałtowca dla przychodu rocznego."""
    for threshold, multiplier in params.lump_sum_health_thresholds:
        if threshold is None or annual_revenue <= threshold:
            return multiplier, money(params.q4_average_wage * multiplier)
    raise AssertionError("progi bez górnej granicy")  # pragma: no cover


def lump_sum_health_contribution(year: int, cumulative_revenue: Decimal) -> dict:
    """Miesięczna składka zdrowotna na ryczałcie.

    `cumulative_revenue` — przychód od początku roku do końca miesiąca, za który liczona
    jest składka, pomniejszony o odliczone składki społeczne. Po przekroczeniu progu
    wyższa składka obowiązuje od miesiąca przekroczenia; wyrównanie za cały rok następuje
    w rozliczeniu rocznym.
    """
    params = get_year_params(year)
    multiplier, base = lump_sum_health_tier(params, cumulative_revenue)
    return {
        "podstawa": base,
        "mnoznik_przecietnego_wynagrodzenia": multiplier,
        "przychod_narastajaco": money(cumulative_revenue),
        "skladka": pct(base, params.health_rate),
    }


def health_contribution(
    year: int, profile: ContributionProfile, cumulative_revenue: Decimal
) -> dict:
    if profile.tax_form == "ryczalt_ewidencjonowany":
        return lump_sum_health_contribution(year, cumulative_revenue)
    raise UnsupportedTaxForm(
        "Składka zdrowotna dla skali i podatku liniowego wymaga ewidencji kosztów (KPiR) — "
        "na razie obsługiwany jest tylko ryczałt."
    )
