"""Parametry składek i ryczałtu na poszczególne lata.

Każdy rok to osobny, niezmienny zestaw liczb. Nowy rok = nowy wpis w YEAR_PARAMS
(z podaniem źródła), nigdy edycja istniejącego.

Źródła (zweryfikowane X 2026):
- 2026: płaca minimalna 4806 zł, prognozowane przeciętne wynagrodzenie 9420 zł,
  przeciętne wynagrodzenie w IV kw. 2025 z wypłatami z zysku 9228,64 zł (GUS, 22.01.2026),
  minimalna podstawa zdrowotnej (skala/liniowy) od II 2026: 100% płacy minimalnej.
- 2025: płaca minimalna 4666 zł, prognozowane przeciętne wynagrodzenie 8673 zł,
  przeciętne wynagrodzenie w IV kw. 2024 z wypłatami z zysku 8549,18 zł,
  minimalna podstawa zdrowotnej (skala/liniowy) II 2025 – I 2026: 75% płacy minimalnej.
"""

from dataclasses import dataclass
from decimal import Decimal

D = Decimal


class MissingYearParams(LookupError):
    """Brak parametrów dla danego roku — trzeba dopisać wpis w YEAR_PARAMS."""


@dataclass(frozen=True)
class YearParams:
    year: int
    minimum_wage: Decimal
    forecast_average_wage: Decimal
    # Przeciętne wynagrodzenie w sektorze przedsiębiorstw w IV kw. roku poprzedniego
    # (z wypłatami z zysku) — podstawa składki zdrowotnej na ryczałcie.
    q4_average_wage: Decimal
    # Ułamek płacy minimalnej będący minimalną podstawą zdrowotnej (skala/liniowy)
    # w roku składkowym zaczynającym się 1 lutego tego roku.
    health_min_base_share: Decimal

    # Stawki składek społecznych (procenty)
    pension_rate: Decimal = D("19.52")
    disability_rate: Decimal = D("8.00")
    sickness_rate: Decimal = D("2.45")
    accident_rate: Decimal = D("1.67")
    labor_fund_rate: Decimal = D("2.45")  # Fundusz Pracy + Fundusz Solidarnościowy

    health_rate: Decimal = D("9.00")
    health_rate_linear: Decimal = D("4.90")

    # Progi przychodu dla składki zdrowotnej na ryczałcie i mnożniki podstawy
    lump_sum_health_thresholds: tuple = (
        (D("60000"), D("0.60")),
        (D("300000"), D("1.00")),
        (None, D("1.80")),
    )

    @property
    def full_social_base(self) -> Decimal:
        """Podstawa „dużego ZUS”: 60% prognozowanego przeciętnego wynagrodzenia."""
        return (self.forecast_average_wage * D("0.60")).quantize(D("0.01"))

    @property
    def preferential_social_base(self) -> Decimal:
        """Podstawa preferencyjna: 30% płacy minimalnej."""
        return (self.minimum_wage * D("0.30")).quantize(D("0.01"))

    @property
    def health_min_base(self) -> Decimal:
        """Minimalna podstawa zdrowotnej dla skali/liniowego (od lutego tego roku)."""
        return (self.minimum_wage * self.health_min_base_share).quantize(D("0.01"))


YEAR_PARAMS: dict[int, YearParams] = {
    2025: YearParams(
        year=2025,
        minimum_wage=D("4666.00"),
        forecast_average_wage=D("8673.00"),
        q4_average_wage=D("8549.18"),
        health_min_base_share=D("0.75"),
    ),
    2026: YearParams(
        year=2026,
        minimum_wage=D("4806.00"),
        forecast_average_wage=D("9420.00"),
        q4_average_wage=D("9228.64"),
        health_min_base_share=D("1.00"),
    ),
}


def get_year_params(year: int) -> YearParams:
    try:
        return YEAR_PARAMS[year]
    except KeyError:
        known = ", ".join(str(y) for y in sorted(YEAR_PARAMS))
        raise MissingYearParams(
            f"Brak parametrów składek dla roku {year} (dostępne: {known}). "
            "Dopisz rok w ksiegowosc/tax_engine/params.py."
        ) from None
