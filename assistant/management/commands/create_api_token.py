from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from assistant.models import ApiToken


class Command(BaseCommand):
    help = "Tworzy token API dla serwera MCP (token wyświetlany jest tylko raz)."

    def add_arguments(self, parser):
        parser.add_argument(
            "username", help="Użytkownik, w którego imieniu działa token"
        )
        parser.add_argument(
            "--name",
            default="Klient MCP",
            help="Opis tokena, np. 'Claude Code — laptop'",
        )
        parser.add_argument(
            "--write",
            action="store_true",
            help="Zezwól na zapis (rozliczenia, import KSeF)",
        )

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist:
            raise CommandError(f"Nie ma użytkownika {options['username']!r}") from None
        token, raw = ApiToken.issue(user, options["name"], can_write=options["write"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Utworzono token „{token.name}” (uprawnienia: {', '.join(token.scopes)})."
            )
        )
        self.stdout.write("Zapisz go teraz — nie da się go później odczytać:\n")
        self.stdout.write(raw)
