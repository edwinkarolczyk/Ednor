# EDNOR — Proces i bramki statusów

## Statusy `quote`

- `draft` — wersja robocza, edytowalna wewnętrznie.
- `sent` — wycena wysłana do klienta.
- `accepted` — wycena zaakceptowana przez klienta.
- `rejected` — wycena odrzucona.

## Statusy `order`

- `awaiting_deposit` — oczekiwanie na zaliczkę po akceptacji wyceny.
- `ready_for_production` — można uruchomić produkcję.
- `in_production` — produkcja w toku.
- `ready_for_installation` — gotowe do montażu.
- `in_installation` — montaż w toku.
- `completed` — realizacja zakończona.
- `service` — zlecenie serwisowe / obsługa posprzedażowa.
- `cancelled` — anulowane.

## Reguły bramkowe

1. **Bez akceptacji i zaliczki nie startuje produkcja.**
2. **Bez materiału/rezerwacji nie startuje produkcja.**
3. Zmiana `quote` na `accepted` nie tworzy zlecenia automatycznie, dopóki zaliczka nie ma statusu „zapłacona”.
4. Utworzone `order` dziedziczy kluczowe dane z wyceny (klient, adres, źródło wyceny).

## Przepływ docelowy (Model B)

`quote:draft` → `quote:sent` → `quote:accepted` + `deposit:paid` → `order:awaiting_deposit/ready_for_production` → produkcja → montaż → serwis
