# Ednor — wersja portable

Ednor jest projektowany jako program portable pod warsztat.

Docelowy układ:

```text
Ednor.exe
Ednor_data/
  config.json
  magazyn/
    cutting_materials.json
    stock_bars.json
    stock_moves.jsonl
  transporty/
    transports.json
  rozkroj/
    settings.json
    calculations/
    reports/
```

Program nie powinien zapisywać danych do:

```text
AppData
Program Files
_MEIPASS
```

Dane mają leżeć obok `Ednor.exe` albo obok plików projektu przy uruchomieniu przez:

```bat
start.bat
```

## Uruchomienie z kodu

```bat
start.bat
```

albo:

```bash
py gui_cutting.py
```

## Test core

Przed budową EXE warto odpalić:

```bat
check_ednor_core.bat
```

albo:

```bash
py check_ednor_core.py
```

Test sprawdza:

- tworzenie `Ednor_data`,
- dodanie surowca,
- dodanie transportu,
- dopisanie sztang do magazynu,
- FIFO przy akceptacji kalkulacji,
- dziedziczenie ceny i transportu przez odpad,
- blokadę podwójnej akceptacji,
- backup JSON `.bak`,
- ochronę zepsutego JSON jako `.broken_TIMESTAMP`.

## Budowa EXE

```bat
build_exe.bat
```

Po budowie plik powinien być tutaj:

```text
dist/Ednor.exe
```

## Test EXE portable

1. Skopiuj `dist/Ednor.exe` do pustego folderu.
2. Uruchom `Ednor.exe`.
3. Program powinien sam utworzyć `Ednor_data`.
4. Dodaj surowiec.
5. Dodaj transport.
6. Dodaj rozkrój.
7. Zamknij program.
8. Uruchom ponownie.
9. Dane powinny zostać w `Ednor_data`.

## Ważne zasady

- Surowców nie kasujemy fizycznie — ustawiamy `aktywny=false`.
- Transportów nie kasujemy.
- Akceptacja kalkulacji zdejmuje materiał z magazynu.
- Druga akceptacja tej samej kalkulacji ma być zablokowana.
- Odpad po cięciu ma wracać do magazynu z `transport_id`, `line_id`, ceną i VAT.
- JSON-y mają backup `.bak` przy zapisie.
- Zepsuty JSON ma zostać przeniesiony do `.broken_TIMESTAMP`.

## Minimalny test kompilacji

```bash
py -m py_compile gui_cutting.py core/cutting_storage.py core/ednor_paths.py check_ednor_core.py
```
