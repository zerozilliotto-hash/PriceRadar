"""
Configurazione centrale del progetto Vinted Hunter.

Tutte le impostazioni modificabili sono qui. Le credenziali (token, API key)
vanno messe in un file ".env" separato (vedi .env.example) e NON in questo
file, per non rischiare di pubblicarle per errore se condividi il codice.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # legge il file .env nella stessa cartella


# ----------------------------------------------------------------------------
# CREDENZIALI (lette da variabili d'ambiente / file .env)
# ----------------------------------------------------------------------------

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


# ----------------------------------------------------------------------------
# RICERCHE
# ----------------------------------------------------------------------------

VINTED_DOMAIN = "https://www.vinted.it"
EBAY_MARKETPLACE = "EBAY_IT"  # cambia in base al tuo paese (EBAY_US, EBAY_GB, ...)

# Quali marketplace interrogare ad ogni ciclo. Disattiva quelli che non ti
# interessano per velocizzare le ricerche e ridurre il rischio di ban.
MARKETPLACE_ATTIVI = {
    "vinted": True,
    "ebay": True,       # serve EBAY_CLIENT_ID/SECRET in .env, altrimenti viene saltato
    "depop": True,
    "subito": True,
}

# Ogni "profilo di ricerca" è un gruppo di keyword sinonime + i filtri.
# Aggiungi quanti profili vuoi.
SEARCH_PROFILES = [
    {
        "nome": "Nike Tech Fleece",
        "keywords": ["Nike Tech Fleece", "Nike Tech", "Tech Fleece", "TF Nike"],
        "prezzo_max": 80.0,
        "taglie_accettate": None,  # es. ["S", "M"] oppure None per tutte
    },
    # Aggiungi altri profili qui, es.:
    # {
    #     "nome": "Stone Island Giubbotto",
    #     "keywords": ["Stone Island giubbotto", "Stone Island jacket"],
    #     "prezzo_max": 150.0,
    #     "taglie_accettate": ["M", "L"],
    # },
]

# Quanto sotto il prezzo medio di mercato deve essere un annuncio per essere
# segnalato come "affare" (0.25 = 25% sotto la media)
SOGLIA_AFFARE = 0.25

# Quanti annunci storici servono come minimo prima di calcolare un prezzo
# medio attendibile per una keyword
MIN_CAMPIONI_PER_MEDIA = 5


# ----------------------------------------------------------------------------
# RATE LIMITING / TIMING
# ----------------------------------------------------------------------------

DELAY_TRA_RICERCHE_SECONDI = 3.0      # pausa tra una keyword e l'altra
INTERVALLO_CICLO_MINUTI = 10          # ogni quanto ripetere tutto il giro


# ----------------------------------------------------------------------------
# NOTIFICHE
# ----------------------------------------------------------------------------

INVIA_FOTO_IN_NOTIFICA = True  # invia la foto dell'annuncio nel messaggio Telegram, non solo il link


# ----------------------------------------------------------------------------
# MODELLO PREZZI (statistico/ML)
# ----------------------------------------------------------------------------

# "mediana": usa solo media/mediana storica (il comportamento originale,
#            semplice e trasparente)
# "ml": usa un modello di regressione che pesa anche marca, taglia,
#       piattaforma - richiede più campioni storici per essere accurato
#       (vedi MIN_CAMPIONI_PER_MODELLO_ML)
MODELLO_PREZZO = "ml"  # oppure "mediana"

MIN_CAMPIONI_PER_MODELLO_ML = 20  # sotto questa soglia si usa comunque la mediana come fallback


# ----------------------------------------------------------------------------
# SCORE FINALE / RANKING (vedi ranking.py)
# ----------------------------------------------------------------------------

# Pesi delle componenti dello score finale (devono sommare a 1.0).
# Aumenta un peso per dare piu importanza a quella componente.
PESI_SCORE = {
    "prezzo": 0.35,         # quanto e sotto il prezzo medio di mercato
    "affidabilita": 0.25,   # punteggio AI di affidabilita della descrizione
    "fraud": 0.20,          # inverso del rischio rilevato da fraud_detector
    "foto": 0.10,           # presenza foto e assenza di anomalie visive
    "marketplace": 0.10,    # bonus/malus per piattaforma, vedi sotto
}

# Bonus/malus per marketplace (0-100, 50 = neutro). Esempio: ti fidi di piu
# di eBay (API ufficiale, piu controlli) rispetto a uno scraping non
# ufficiale? Alzalo. Personalizza secondo la tua esperienza.
PESI_MARKETPLACE = {
    "vinted": 55.0,
    "ebay": 65.0,
    "depop": 50.0,
    "subito": 45.0,
}

# Soglia di score_finale sopra la quale un annuncio puo entrare nella
# categoria "AFFARI ECCELLENTI" (notifica automatica immediata via Telegram)
SOGLIA_AFFARE_ECCELLENTE = 75.0

# Affidabilita minima richiesta in aggiunta allo score per essere "eccellente"
SOGLIA_AFFIDABILITA_MINIMA_ECCELLENTE = 60

# Numero massimo di "affari eccellenti" inviati automaticamente per ciclo
MAX_AFFARI_ECCELLENTI_PER_CICLO = 5

# Quanti altri annunci interessanti (non eccellenti) tenere disponibili per
# il bottone "Mostra altri" nel bot interattivo, oltre ai 5 eccellenti
MAX_ALTRI_ANNUNCI_INTERESSANTI = 30

# Quanti risultati mostrare per pagina nel bot interattivo (paginazione)
RISULTATI_PER_PAGINA = 5


# ----------------------------------------------------------------------------
# BOT TELEGRAM INTERATTIVO
# ----------------------------------------------------------------------------

# URL della dashboard web, mostrato nel bot col bottone "Apri Dashboard".
# Se la dashboard e solo locale, lascia localhost. Se la esponi tramite
# reverse proxy (vedi README), metti qui l'URL pubblico.
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:5000")

# Quanti marketplace/keyword interrogare al massimo per una ricerca libera
# fatta da Telegram (per evitare che un utente scateni una ricerca enorme
# scrivendo una frase generica). Le ricerche da Telegram sono sempre
# temporanee: non modificano config.SEARCH_PROFILES.
MAX_KEYWORD_RICERCA_LIBERA = 1  # la frase scritta diventa una singola keyword


# ----------------------------------------------------------------------------
# DATABASE
# ----------------------------------------------------------------------------

DB_PATH = "vinted_hunter.db"


# ----------------------------------------------------------------------------
# AI / ANALISI AVANZATA (richiedono ANTHROPIC_API_KEY)
# ----------------------------------------------------------------------------

ABILITA_VALUTAZIONE_AFFIDABILITA = True   # valuta se la descrizione è sospetta
ABILITA_SUGGERIMENTO_PREZZO = True        # suggerisce un prezzo da offrire
ABILITA_ANALISI_FOTO = False              # analisi immagini (più costosa, opzionale)

# Modello da usare per le chiamate testuali e per la vision
MODELLO_TESTO = "claude-sonnet-4-6"
MODELLO_VISION = "claude-sonnet-4-6"


# ----------------------------------------------------------------------------
# v2.0 - RICONOSCIMENTO PRODOTTO INTELLIGENTE (vedi product_recognition.py)
# ----------------------------------------------------------------------------
# Tutte le funzionalita di questa sezione richiedono ANTHROPIC_API_KEY.
# Punto 15 della richiesta: ogni funzionalita ha il proprio flag, cosi puoi
# attivare solo quello che ti serve e tenere sotto controllo i costi/tempi.

# Riconosce automaticamente marca, modello, categoria, collezione, edizione,
# anno, materiale, condizione, genere, collaborazioni (punto 1, 3)
ABILITA_RICONOSCIMENTO_PRODOTTO = True

# Riconosce colore principale e colori secondari da titolo/descrizione
# (punto 2). Se ABILITA_ANALISI_FOTO e' anche attivo, il colore puo essere
# confermato/integrato anche dall'analisi immagine.
ABILITA_RICONOSCIMENTO_COLORE = True

# Quanti giorni un'estrazione attributi resta valida prima di essere
# ricalcolata se l'annuncio viene rianalizzato (punto 16, caching)
GIORNI_VALIDITA_ATTRIBUTI = 30


# ----------------------------------------------------------------------------
# v2.0 - TRADUZIONE AUTOMATICA (vedi translation.py)
# ----------------------------------------------------------------------------

ABILITA_TRADUZIONE_AUTOMATICA = True   # punto 4
LINGUA_DEFAULT = "it"                   # lingua di destinazione per le traduzioni

# Lingue di partenza riconosciute esplicitamente (oltre a queste, il
# rilevamento lingua e' comunque automatico - questa lista serve solo come
# riferimento/documentazione per l'espansione multilingua delle ricerche)
LINGUE_SUPPORTATE = ["it", "en", "fr", "de", "es", "nl"]

# Quanti giorni una traduzione resta valida prima di essere rifatta se
# l'annuncio viene rianalizzato (punto 16, caching - traduciamo una sola volta)
GIORNI_VALIDITA_TRADUZIONE = 90  # il testo originale di un annuncio non cambia quasi mai


# ----------------------------------------------------------------------------
# v2.0 - RICERCA MULTILINGUA E QUERY NATURALE (vedi query_parser.py)
# ----------------------------------------------------------------------------

# Espande automaticamente le keyword nelle principali lingue supportate
# (punto 5). Es. "maglia adidas" -> cerca anche "Adidas shirt", "Adidas jersey"
ABILITA_ESPANSIONE_MULTILINGUA = True

# Interpreta richieste in linguaggio naturale tipo "Jordan 4 bianca sotto i
# 170 euro" estraendo marca/modello/colore/taglia/prezzo (punto 13)
ABILITA_PARSING_QUERY_NATURALE = True


# ----------------------------------------------------------------------------
# v2.0 - OCR E ANALISI IMMAGINE AVANZATA (vedi image_analyzer.py)
# ----------------------------------------------------------------------------

# Legge il testo presente nelle immagini (taglie, etichette, codici - punto 6)
ABILITA_OCR = False  # disabilitato di default: piu chiamate AI, piu costo/tempo

# Rilevamento avanzato: difetti, usura, macchie, scolorimento, pieghe,
# scarpe spaiate, foto duplicate, sfondo sospetto, immagini da catalogo
# (punto 7). Si appoggia allo stesso flag ABILITA_ANALISI_FOTO sopra: questo
# flag ne estende la profondita' di analisi quando gia' attiva.
ABILITA_ANALISI_DIFETTI_AVANZATA = False


# ----------------------------------------------------------------------------
# v2.0 - REVERSE IMAGE SEARCH (vedi reverse_image_search.py)
# ----------------------------------------------------------------------------
# Punto 8 della richiesta: SOLO interfaccia astratta, nessun servizio esterno
# non ufficiale collegato. Questo flag esiste gia' pronto per quando in
# futuro vorrai collegare un provider ufficiale (es. Google Vision API).
ABILITA_REVERSE_IMAGE_SEARCH = False
REVERSE_IMAGE_SEARCH_PROVIDER = None   # nessun provider configurato di default


# ----------------------------------------------------------------------------
# v2.0 - VALUTAZIONE VENDITORE (vedi seller_score.py)
# ----------------------------------------------------------------------------

ABILITA_SCORE_VENDITORE = True   # punto 9

# Quanti giorni un profilo venditore calcolato resta valido prima di essere
# ricalcolato (punto 16, caching - lo score venditore cambia lentamente)
GIORNI_VALIDITA_PROFILO_VENDITORE = 14

# Pesi delle componenti dello score venditore (devono sommare a 1.0)
PESI_SCORE_VENDITORE = {
    "feedback": 0.35,            # rapporto feedback positivi/totali
    "anzianita": 0.15,           # da quanto tempo esiste l'account
    "volume_vendite": 0.20,      # numero di vendite/articoli
    "tempo_risposta": 0.10,      # quanto velocemente risponde
    "coerenza_annunci": 0.20,    # quanto gli annunci dello stesso venditore sono coerenti tra loro
}


# ----------------------------------------------------------------------------
# v2.0 - STIMA PROFITTO (vedi profit_calculator.py)
# ----------------------------------------------------------------------------

ABILITA_STIMA_PROFITTO = True   # punto 10

# Margine di costi forfettario da sottrarre al ROI/profitto stimato, per
# tenere conto di spese accessorie tipiche del reselling (spedizione,
# commissioni piattaforma, eventuale margine di trattativa). Espresso come
# percentuale del prezzo d'acquisto.
MARGINE_COSTI_PERCENTO = 12.0


# ----------------------------------------------------------------------------
# v2.0 - SCORE FINALE: nuova componente venditore
# ----------------------------------------------------------------------------
# Estende PESI_SCORE (sopra) con il punteggio venditore. Se modifichi questi
# pesi, assicurati che la somma di tutti i pesi in PESI_SCORE torni a 1.0.
PESI_SCORE["venditore"] = 0.10
# Per mantenere la somma a 1.0 riduciamo leggermente gli altri pesi storici
# in proporzione, cosi il comportamento esistente non cambia bruscamente
# introducendo questa nuova componente.
_fattore_riduzione = 0.90
for _chiave in ("prezzo", "affidabilita", "fraud", "foto", "marketplace"):
    PESI_SCORE[_chiave] = round(PESI_SCORE[_chiave] * _fattore_riduzione, 4)
