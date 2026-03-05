# ROADMAP

## Etapy rozwoju

- [ ] **Etap 1 — WEB skeleton**
  - **Definition of Done:**
    - Uruchamialna aplikacja web z podstawową strukturą modułów.
    - Konfiguracja środowisk (dev/test/prod) i bazowy deployment.
    - Podstawowy layout i nawigacja.

- [ ] **Etap 2 — logowanie + role + zlecenia podstawowe**
  - **Definition of Done:**
    - Logowanie użytkowników i bezpieczne sesje.
    - Role/uprawnienia (np. admin, biuro, produkcja, montaż).
    - CRUD podstawowych zleceń i lista z filtrami.

- [ ] **Etap 3 — wyceny + ogrodzenia v1 + PDF**
  - **Definition of Done:**
    - Tworzenie i edycja wycen z pozycjami.
    - Kalkulacja wariantów ogrodzeń v1.
    - Generowanie PDF wyceny i zapis historii dokumentu.

- [ ] **Etap 3.5 — timetracking START/STOP (montaż/produkcja/serwis)**
  - **Definition of Done:**
    - Rejestrowanie czasu START/STOP per użytkownik i zlecenie.
    - Kategorie pracy: montaż, produkcja, serwis.
    - Podsumowanie czasu na poziomie zlecenia i użytkownika.

- [ ] **Etap 3.6 — Model B: Akceptacja wyceny + Zaliczka → utworzenie Zlecenia**
  - **Definition of Done:**
    - Statusy wyceny: wysłana/zaakceptowana/odrzucona.
    - Rejestracja zaliczki i statusu płatności.
    - Automatyczne utworzenie `orders` po spełnieniu warunku: akceptacja + wpłata.
    - Powiązanie zlecenia ze źródłową wyceną.

- [ ] **Etap 4 — magazyn + historia cen + rezerwacje + braki**
  - **Definition of Done:**
    - Ewidencja stanów magazynowych i ruchów.
    - Historia cen materiałów.
    - Rezerwacje materiałów pod zlecenia.
    - Sygnalizacja braków materiałowych.

- [ ] **Etap 5 — produkcja (lista elementów + odhaczanie + zdjęcia)**
  - **Definition of Done:**
    - Lista elementów do wykonania dla zlecenia.
    - Odhaczanie postępu produkcji.
    - Dodawanie zdjęć z produkcji i archiwizacja.

- [ ] **Etap 6 — kalendarz globalny (blokady produkcja→montaż)**
  - **Definition of Done:**
    - Jeden kalendarz dla produkcji i montażu.
    - Blokady terminów wynikające z zależności procesu.
    - Walidacja konfliktów zasobów i ekip.

- [ ] **Etap 7 — raporty (zysk/strata, czas pracy, ranking zleceń)**
  - **Definition of Done:**
    - Raport zysk/strata per zlecenie.
    - Raport czasu pracy i obciążenia zespołów.
    - Ranking zleceń wg marży, czasu i terminowości.
