# Architektura

## Moduły

- **Zlecenia**: struktury danych dla zleceń, materiałów, kosztów i statusów.
- **Magazyn**: struktury danych dla materiałów, stanów i ruchów.
- **Klienci**: dane klientów, załączników i notatek.
- **Podwykonawcy**: bazowa ewidencja kontrahentów.
- **Wyceny/Raporty**: szablony wycen i widoki zestawień.
- **Ustawienia**: definicje statusów, jednostek, priorytetów i alertów.

## Zależności

- Moduły korzystają z bazowych struktur (`app/database/models_base.py`).
- UI korzysta z modułów i rdzenia (`app/core`).

## Założenia

- Brak logiki biznesowej i automatycznych obliczeń.
- Wszystkie wartości edytowalne w ustawieniach.
- Struktura przygotowana do dalszej rozbudowy.
