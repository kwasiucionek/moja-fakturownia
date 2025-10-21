# ksiegowosc/utils.py

def add_pwa_headers(headers, path, url):
    """
    Dodaje nagłówek Service-Worker-Allowed do pliku sw.js.
    Pozwala to na rejestrację Service Workera w głównym zakresie ('/'),
    nawet jeśli sam plik sw.js jest serwowany z innego katalogu (np. /static/).
    """
    if url == '/static/sw.js':
        headers['Service-Worker-Allowed'] = '/'
