from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from assistant.agents import close_month
from ksiegowosc.models import CompanyInfo
from ksiegowosc.settlements import SettlementError
from ksiegowosc.tax_engine.calendar import previous_month


class Command(BaseCommand):
    help = "Agent zamknięcia miesiąca: należności ZUS i ryczałtu, kontrola kompletności, szkic rozliczenia i raport."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)
        parser.add_argument("--month", type=int)
        parser.add_argument(
            "--user",
            help="Nazwa użytkownika (domyślnie wszyscy z uzupełnionymi danymi firmy)",
        )
        parser.add_argument(
            "--no-draft", action="store_true", help="Tylko raport, bez zapisu szkicu"
        )

    def handle(self, *args, **opts):
        if opts["year"] and opts["month"]:
            year, month = opts["year"], opts["month"]
        elif opts["year"] or opts["month"]:
            raise CommandError(
                "Podaj jednocześnie --year i --month albo żadnego (poprzedni miesiąc)."
            )
        else:
            today = timezone.localdate()
            year, month = previous_month(today.year, today.month)

        user_ids = CompanyInfo.objects.values_list("user_id", flat=True)
        users = User.objects.filter(pk__in=user_ids, is_active=True)
        if opts["user"]:
            users = users.filter(username=opts["user"])
            if not users.exists():
                raise CommandError(f"Brak użytkownika {opts['user']!r} z danymi firmy.")

        failures, done = 0, 0
        for user in users:
            try:
                report = close_month(user, year, month, save_draft=not opts["no_draft"])
            except SettlementError as exc:
                failures += 1
                self.stderr.write(f"{user.username}: {exc}")
                continue
            done += 1
            self.stdout.write(f"{user.username}: {report.title}")
        # Błąd zwracamy tylko, gdy nie udało się dla nikogo (np. brak parametrów roku)
        if failures and not done:
            raise CommandError(f"Nie udało się dla żadnego użytkownika ({failures}).")
