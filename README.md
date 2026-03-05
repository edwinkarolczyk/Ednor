# Ednor — WEB skeleton (Etap 2)

Minimalna aplikacja demo oparta o **FastAPI** z logowaniem, rolami i przypisaniami do zleceń.

## Uruchomienie na Windows

1. Kliknij dwukrotnie plik `run_dev.bat`.
2. Skrypt utworzy środowisko `venv`, zainstaluje zależności i uruchomi serwer.

## Login (demo)

- `admin / admin123`
- ⚠️ To hasło jest tylko do demo i powinno być zmienione poza środowiskiem testowym.

## Role

- Produkcja
- Monter
- Serwisant
- Admin

## Widoki

- `/login`
- `/my-orders`
- `/orders` (admin)
- `/users` (admin)
- `/me`

## Upload placeholder

Endpoint `POST /api/orders/{order_id}/upload` zapisuje pliki do katalogu:

`uploads/{order_id}/`
