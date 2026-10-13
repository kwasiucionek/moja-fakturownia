"""Silnik obliczeń: składki ZUS, ryczałt, terminy.

Moduł nie korzysta z ORM — przyjmuje i zwraca liczby (Decimal), dzięki czemu jest
w pełni testowalny. Pobieranie danych z bazy: ksiegowosc.settlements.
"""

from .calendar import (
    annual_health_deadline,
    annual_return_deadline,
    lump_sum_deadline,
    shift_to_working_day,
    zus_deadline,
)
from .contributions import (
    ZUS_VARIANT_LABELS,
    ContributionProfile,
    UnsupportedTaxForm,
    health_contribution,
    lump_sum_health_contribution,
    social_contributions,
)
from .lump_sum import LumpSumResult, lump_sum_tax
from .params import YEAR_PARAMS, MissingYearParams, YearParams, get_year_params

__all__ = [
    "YEAR_PARAMS",
    "ZUS_VARIANT_LABELS",
    "ContributionProfile",
    "LumpSumResult",
    "MissingYearParams",
    "UnsupportedTaxForm",
    "YearParams",
    "annual_health_deadline",
    "annual_return_deadline",
    "get_year_params",
    "health_contribution",
    "lump_sum_deadline",
    "lump_sum_health_contribution",
    "lump_sum_tax",
    "shift_to_working_day",
    "social_contributions",
    "zus_deadline",
]
