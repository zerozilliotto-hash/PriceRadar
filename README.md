# Vinted Hunter v2.0 — Assistente AI per il Reselling

Sistema completo che trasforma la ricerca su marketplace second-hand da
semplice scraping con keyword in un vero assistente AI per il reselling:
riconosce prodotti, traduce annunci, parla in linguaggio naturale, calcola
profitto e ROI, valuta i venditori, e analizza le foto.

---

## Architettura v2.0

```
vinted_hunter/
│
│  FONDAMENTA (invariate e retrocompatibili)
├── config.py                  # configurazione centrale, ora con ~40 flag
├── database.py                # SQLite: 50 colonne su annunci, migrazione automatica
│
│  RICERCA E RACCOLTA (invariati)
├── vinted_client.py           # Vinted (scraping non ufficiale)
├── ebay_client.py             # eBay (API ufficiale)
├── depop_client.py            # Depop (scraping HTML + JSON-LD)
├── subito_client.py           # Subito.it (scraping HTML + JSON-LD)
│
│  INTELLIGENZA v2.0 (nuovi moduli)
├── product_recognition.py     # NUOVO: estrae marca/modello/colore/attributi via AI
├── translation.py             # NUOVO: traduzione automatica con caching
├── query_parser.py            # NUOVO: NLU per query naturale + espansione multilingua
├── seller_score.py            # NUOVO: valutazione venditore (0-100)
├── profit_calculator.py       # NUOVO: stima profitto, ROI, risparmio
├── reverse_image_search.py    # NUOVO: interfaccia astratta (nessun servizio non ufficiale)
│
│  ANALISI ESISTENTI (estesi)
├── price_analyzer.py          # stima prezzi (mediana o ML Ridge)
├── price_ml_model.py          # regressione Ridge su marca/taglia/piattaforma
├── fraud_detector.py          # regole esplicite per pattern sospetti
├── ai_advisor.py              # AI: affidabilità + prezzo offerta
├── image_analyzer.py          # ESTESO: OCR + difetti avanzati + analisi base
├── ranking.py                 # ESTESO: ora include componente venditore
│
│  ORCHESTRAZIONE (estesi)
├── main.py                    # ESTESO: pipeline analisi a 10 step
├── telegram_bot.py            # notifiche push (invariato)
│
│  BOT INTERATTIVO (estesi)
├── telegram_state.py          # stato sessione per chat
├── telegram_filters.py        # filtri e ordinamento
├── telegram_search.py         # ESTESO: integra query parser + espansione multilingua
├── telegram_favorites.py      # preferiti
├── telegram_buttons.py        # ESTESO: aggiunti "Ricerca simili" e "Testo originale"
├── telegram_menu.py           # ESTESO: mostra ROI, profitto, modello, difetti
├── telegram_pagination.py     # paginazione
├── telegram_handlers.py       # ESTESO: gestisce cerca_simili, mostra_originale
├── telegram_interactive_bot.py # entry point bot interattivo
│
│  DASHBOARD (estesa)
├── webapp/
│   ├── app.py                 # ESTESO: nuovi endpoint trend, statistiche globali, filtri
│   └── templates/dashboard.html # ESTESO: grafico prezzi, filtri attributo, ROI
│
│  TEST
├── tests/
│   ├── test_database.py            # 14 test schema, migrazione, salvataggio
│   ├── test_ranking_profit_seller.py # 21 test ranking, profitto, venditore
│   ├── test_ai_modules_no_api.py   # 19 test caching e fallback senza API
│   └── test_integration.py         # 8 test pipeline end-to-end
│
├── requirements.txt
└── .env.example
```

---

## Nuove funzionalità v2.0

### 1. Riconoscimento prodotto intelligente (`product_recognition.py`)
Ogni annuncio viene analizzato da Claude per estrarre automaticamente:
marca, modello specifico, categoria, sottocategoria, collezione, edizione
(colorway), anno, materiale, condizione, genere, collaborazioni,
limited edition. Una singola chiamata AI estrae **tutti gli attributi**
insieme (più efficiente di chiamate separate).

```
"Air Jordan 4 Retro Bred Reimagined GS" →
  modello: "Air Jordan 4"
  collezione: "Retro"
  edizione: "Bred Reimagined"
  limited_edition: true
```

**Caching**: gli attributi vengono estratti una volta e salvati nel
database. Non vengono ricalcolati per `GIORNI_VALIDITA_ATTRIBUTI` giorni
(default: 30). Disattivabile con `ABILITA_RICONOSCIMENTO_PRODOTTO = False`.

### 2. Riconoscimento colori (`product_recognition.py`)
Estratti insieme agli altri attributi: `colore_principale` e
`colori_secondari` (JSON list). La ricerca "Nike Tech grigia" può filtrare
per colore dalla dashboard v2.0.

### 3. Traduzione automatica (`translation.py`)
Se il titolo/descrizione di un annuncio non è in italiano, Claude lo
traduce automaticamente mantenendo invariati brand, modelli e taglie.
Il testo originale viene sempre conservato (`titolo_originale`,
`descrizione_originale`). Il bottone "Testo originale" nel bot Telegram
mostra la versione pre-traduzione.

**Caching**: una traduzione valida per `GIORNI_VALIDITA_TRADUZIONE` giorni
(default: 90) non viene rifatta. Un'euristica veloce (parole italiane comuni)
evita chiamate AI su annunci già in italiano.

### 4. Ricerca in linguaggio naturale (`query_parser.py`)
L'utente può scrivere al bot frasi naturali come:

```
"Cerco una Jordan 4 bianca sotto i 170 euro"
```

Il parser estrae: `marca="Nike"`, `modello="Air Jordan 4"`,
`colore="bianco"`, `prezzo_max=170.0`. I filtri vengono automaticamente
pre-impostati nella sessione di ricerca.

Anche senza API key e con `ABILITA_PARSING_QUERY_NATURALE = True`, esiste
un fallback locale per i casi piu comuni: colori, taglie, prezzo massimo,
marketplace, brand frequenti e modelli come Jordan 4 / Nike Tech Fleece.

### 5. Espansione multilingua (`query_parser.py`)
"maglia adidas" viene espansa automaticamente in varianti nelle lingue dei
marketplace attivi ("Adidas shirt", "Adidas jersey", "T-shirt Adidas", ecc.)
prima di essere cercata. Massimo 10 keyword per ricerca, la prima è sempre
l'originale. Disattivabile con `ABILITA_ESPANSIONE_MULTILINGUA = False`.

### 6. OCR immagini (`image_analyzer.py`)
Estrae il testo visibile dalle foto dell'annuncio: taglie su etichette,
numeri seriali, scritte sul prodotto, codici. Salvato in `testo_ocr`.
Disabilitato di default (`ABILITA_OCR = False`): costa una chiamata AI
extra per ogni immagine.

### 7. Analisi difetti avanzata (`image_analyzer.py`)
Rileva specificamente: macchie, strappi, usura, scolorimento, pieghe,
scarpe spaiate, suola consumata, sfondo sospetto, immagini da catalogo.
Popola `difetti_rilevati` (JSON list) e `immagine_sospetta` (bool).
Abilitabile con `ABILITA_ANALISI_DIFETTI_AVANZATA = True`.

### 8. Interfaccia Reverse Image Search (`reverse_image_search.py`)
Solo interfaccia astratta (classe `ReverseImageSearchProvider`), nessun
servizio non ufficiale collegato. Quando vorrai collegare un provider
ufficiale (es. Google Vision API):

```python
from reverse_image_search import ReverseImageSearchProvider, registra_provider

class GoogleVisionProvider(ReverseImageSearchProvider):
    def cerca(self, url_immagine: str) -> list[dict]:
        # ... implementa qui
        pass

registra_provider("google_vision", GoogleVisionProvider)
# in .env: REVERSE_IMAGE_SEARCH_PROVIDER=google_vision
```

### 9. Score venditore (`seller_score.py`)
Score 0-100 per ogni venditore basato su: feedback (35%), anzianità
account (15%), volume vendite (20%), tempo risposta (10%), coerenza degli
annunci (20% — calcolata sui dati già nel database, senza API esterne).

**Caching**: il profilo viene ricalcolato ogni `GIORNI_VALIDITA_PROFILO_VENDITORE`
giorni (default: 14). Venditori multipli dello stesso marketplace riusano
automaticamente il profilo calcolato. Entra nel ranking finale come
componente "venditore" (peso: 10%).

### 10. Stima profitto/ROI (`profit_calculator.py`)
Ogni annuncio mostra:

| Campo | Descrizione |
|---|---|
| `valore_stimato` | Prezzo medio storico di mercato |
| `risparmio_euro` | Valore stimato - prezzo (negativo = sopra mercato) |
| `risparmio_percento` | % di sconto rispetto al valore |
| `profitto_stimato` | Risparmio - costi forfettari (`MARGINE_COSTI_PERCENTO`) |
| `roi_stimato` | (Profitto / prezzo) × 100 |
| `margine_percento` | (Profitto / valore stimato) × 100 |

Configurabile: `MARGINE_COSTI_PERCENTO` (default: 12%) copre spedizione,
commissioni piattaforma e margine di rischio. Richiede che `price_analyzer`
abbia già calcolato `prezzo_medio_mercato` (step precedente nella pipeline).

### 11. Telegram v2.0 (`telegram_*`)
Le notifiche automatiche e il bot interattivo usano la stessa card annuncio:
foto quando disponibile, titolo tradotto, prezzo, valore stimato, risparmio,
ROI, profitto, margine, colore, modello, taglia, condizione, marketplace,
venditore, score, affidabilita, difetti/OCR quando presenti.

Bottoni disponibili sotto gli annunci:

- Apri annuncio
- Segna come visto
- Preferiti
- Ignora
- Nascondi simili
- Ricerca simili
- Testo originale quando esiste una traduzione

Il bottone "Mostra altri" riusa i risultati gia salvati e non rifà scraping.
Solo "Aggiorna ricerca" interroga di nuovo i marketplace. Gli ID molto lunghi
di alcuni marketplace vengono convertiti in riferimenti compatti per rispettare
il limite Telegram di 64 byte nei callback.

---

## Pipeline di analisi v2.0

Ogni nuovo annuncio passa attraverso questi step in `main.py`:

```
1. product_recognition.riconosci_prodotto()   → attributi strutturati
2. translation.traduci_annuncio()              → titolo/desc in italiano
3. price_analyzer.analizza_prezzo()            → prezzo medio + is_affare
4. fraud_detector.valuta()                     → pattern sospetti
5. ai_advisor.valuta_affidabilita()            → punteggio affidabilità
6. ai_advisor.suggerisci_prezzo_offerta()      → prezzo da offrire
7. seller_score.calcola_score_venditore()      → punteggio venditore
8. profit_calculator.calcola_profitto()        → ROI, profitto, risparmio
9. image_analyzer.analisi_completa_immagine()  → foto, OCR, difetti
10. ranking.calcola_score()                    → score finale 0-100
    → database.salva_annuncio()
```

Ogni step è **opzionale** (flag in `config.py`) e gestisce i propri
errori senza bloccare i successivi (punto 17, robustezza).

---

## Migrazione database automatica

Il database si aggiorna automaticamente da qualsiasi versione precedente.
Basta avviare il sistema: `database.init_db()` rileva le colonne mancanti
e le aggiunge con `ALTER TABLE`, **senza** cancellare dati esistenti.

Testato esplicitamente con database v1.0 (22 colonne) → v2.0 (50 colonne).

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# compila .env con le tue credenziali
```

### Esegui

```bash
# Motore di ricerca automatica (loop in background)
python3 main.py --loop

# Bot Telegram interattivo
python3 telegram_interactive_bot.py

# Dashboard web
python3 webapp/app.py

# Test suite completa (no API necessarie)
python3 -m pytest -q
```

---

## Configurazione (tutte le nuove flag v2.0 in config.py)

```python
# Riconoscimento prodotto/colori (richiede ANTHROPIC_API_KEY)
ABILITA_RICONOSCIMENTO_PRODOTTO = True
ABILITA_RICONOSCIMENTO_COLORE   = True
GIORNI_VALIDITA_ATTRIBUTI       = 30

# Traduzione automatica
ABILITA_TRADUZIONE_AUTOMATICA   = True
LINGUA_DEFAULT                  = "it"
GIORNI_VALIDITA_TRADUZIONE      = 90

# Query naturale e multilingua
ABILITA_PARSING_QUERY_NATURALE  = True
ABILITA_ESPANSIONE_MULTILINGUA  = True

# OCR e analisi immagini avanzata (disabilitati di default: costosi)
ABILITA_OCR                         = False
ABILITA_ANALISI_DIFETTI_AVANZATA    = False

# Valutazione venditore
ABILITA_SCORE_VENDITORE              = True
GIORNI_VALIDITA_PROFILO_VENDITORE    = 14

# Stima profitto
ABILITA_STIMA_PROFITTO          = True
MARGINE_COSTI_PERCENTO          = 12.0

# Reverse image search (interfaccia pronta, nessun provider collegato)
ABILITA_REVERSE_IMAGE_SEARCH        = False
REVERSE_IMAGE_SEARCH_PROVIDER       = None
```

---

## Eseguire i test

```bash
python3 -m pytest tests/ -v
```

59 test coprono: schema database e migrazione, ranking, profitto, venditore,
caching dei moduli AI, fallback senza credenziali, pipeline end-to-end.
Nessun test richiede API reali o rete.

---

## Limiti onesti (invariati)

- **Vinted, Depop, Subito**: scraping non ufficiale, può rompersi
- **Analisi foto**: non certifica l'autenticità, solo anomalie visive
- **Score venditore**: limitato ai dati disponibili senza accesso autenticato
- **Auto-acquisto**: non implementato di proposito (rischio economico senza supervisione umana)
- **Reverse image search**: solo interfaccia, nessun provider collegato
- **OCR e difetti avanzati**: disabilitati di default per costo AI
