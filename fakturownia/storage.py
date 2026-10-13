from whitenoise.storage import CompressedManifestStaticFilesStorage


class LenientManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Jak CompressedManifestStaticFilesStorage, ale nie wywala się na
    {% static %} wskazującym na ścieżkę, która nie jest realnym, pojedynczym
    plikiem w manifeście — dokładnie to robi szablon admin/base.html
    w django-jazzmin 3.0.5 (data-theme-base="{% static 'vendor/bootswatch' %}",
    czyli static() na SAMYM FOLDERZE, nie na pliku).

    Bez tego: ValueError: Missing staticfiles manifest entry / could not be found.
    Fallback: zwróć niehashowaną ścieżkę zamiast wywalać cały request.
    """

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except ValueError:
            return name
