# ksiegowosc/admin_filters.py

from django.contrib.admin import SimpleListFilter
from django.contrib.auth.models import User
from .models import CompanyInfo


class HasCompanyInfoFilter(SimpleListFilter):
    """Filter dla użytkowników z/bez danych firmy"""
    title = 'dane firmy'
    parameter_name = 'has_company'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Ma dane firmy'),
            ('no', 'Brak danych firmy'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(companyinfo__isnull=False)
        elif self.value() == 'no':
            return queryset.filter(companyinfo__isnull=True)
        return queryset


class UserGroupFilter(SimpleListFilter):
    """Filter dla grup użytkowników"""
    title = 'grupa'
    parameter_name = 'user_group'

    def lookups(self, request, model_admin):
        return (
            ('ksiegowosc', 'Księgowość'),
            ('no_group', 'Bez grupy'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'ksiegowosc':
            return queryset.filter(groups__name='ksiegowosc')
        elif self.value() == 'no_group':
            return queryset.filter(groups__isnull=True)
        return queryset

