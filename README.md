# Ednor — WEB skeleton (Etap 1)

Minimalna aplikacja demo oparta o **FastAPI** z prostym interfejsem webowym i placeholderami modułów.

## Uruchomienie na Windows

1. Kliknij dwukrotnie plik `run_dev.bat`.
2. Skrypt utworzy środowisko `venv`, zainstaluje zależności i uruchomi serwer.

## Adresy

- Lokalnie na komputerze: http://localhost:8000
- Z telefonu (ta sama sieć Wi‑Fi/LAN): http://IP_KOMPUTERA:8000

## Dostępne widoki

- `/` — strona główna
- `/orders` — Zlecenia (placeholder + przycisk Dodaj + prosty upload)
- `/inventory` — Magazyn (placeholder)
- `/calendar` — Kalendarz (placeholder)
- `/api/health` — endpoint zdrowia (`{"status":"ok"}`)

## Upload placeholder

Endpoint `POST /api/orders/{order_id}/upload` zapisuje pliki do katalogu:

`uploads/{order_id}/`
