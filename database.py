"""
Database SQLite per lo storico degli annunci trovati.

Perché SQLite e non CSV:
- Permette query veloci per calcolare prezzo medio/mediano per keyword
- Evita duplicati in modo più robusto
- Singolo file, zero configurazione, perfetto per uso personale

Tabelle:
- annunci: ogni annuncio trovato, con tutti i dati e i flag calcolati
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Iterator
from dataclasses import dataclass, field, asdict

import config


@dataclass
class Annuncio:
    id: str                      # id univoco, prefissato con la piattaforma (es. "vinted_12345")
    piattaforma: str             # "vinted" oppure "ebay"
    titolo: str
    prezzo: float
    valuta: str
    marca: Optional[str] = None
    taglia: Optional[str] = None
    url: str = ""
    foto_url: Optional[str] = None
    descrizione: Optional[str] = None
    venditore: Optional[str] = None
    keyword_trovata: str = ""
    profilo_ricerca: str = ""
    timestamp_trovato: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    # Campi calcolati successivamente (possono essere None finché non analizzati)
    prezzo_medio_mercato: Optional[float] = None
    is_affare: Optional[bool] = None
    punteggio_affidabilita: Optional[int] = None      # 0-100, da AI
    motivo_affidabilita: Optional[str] = None
    prezzo_offerta_suggerito: Optional[float] = None
    esito_analisi_foto: Optional[str] = None          # "autentico" / "dubbio" / "difetti_rilevati" / None
    notificato: bool = False
    score_finale: Optional[float] = None              # punteggio combinato, vedi ranking.py

    # ------------------------------------------------------------------
    # CAMPI v2.0: riconoscimento prodotto intelligente (vedi product_recognition.py)
    # ------------------------------------------------------------------
    modello: Optional[str] = None                     # es. "Air Jordan 4"
    categoria: Optional[str] = None                    # es. "scarpe"
    sottocategoria: Optional[str] = None                # es. "sneakers basse"
    collezione: Optional[str] = None                     # es. "Retro"
    edizione: Optional[str] = None                         # es. "Bred Reimagined"
    anno: Optional[int] = None
    colore_principale: Optional[str] = None
    colori_secondari: Optional[str] = None             # JSON-encoded list, vedi product_recognition.py
    materiale: Optional[str] = None
    condizione: Optional[str] = None                  # es. "nuovo con cartellino", "usato buone condizioni"
    genere: Optional[str] = None                      # es. "uomo", "donna", "unisex"
    collaborazioni: Optional[str] = None               # es. "Travis Scott x Jordan"
    limited_edition: Optional[bool] = None
    attributi_estratti_il: Optional[str] = None        # timestamp dell'ultima estrazione attributi, per caching

    # ------------------------------------------------------------------
    # CAMPI v2.0: traduzione automatica (vedi translation.py)
    # ------------------------------------------------------------------
    lingua_originale: Optional[str] = None             # codice ISO, es. "en", "fr", "de"
    titolo_originale: Optional[str] = None             # testo originale prima della traduzione
    descrizione_originale: Optional[str] = None
    tradotto_il: Optional[str] = None                  # timestamp dell'ultima traduzione, per caching

    # ------------------------------------------------------------------
    # CAMPI v2.0: OCR e analisi immagine avanzata (vedi image_analyzer.py)
    # ------------------------------------------------------------------
    testo_ocr: Optional[str] = None                    # testo estratto dalle immagini
    difetti_rilevati: Optional[str] = None             # JSON-encoded list di difetti (macchie, usura, ecc.)
    immagine_sospetta: Optional[bool] = None            # foto duplicata/da catalogo/sfondo sospetto

    # ------------------------------------------------------------------
    # CAMPI v2.0: punteggio venditore (vedi seller_score.py)
    # ------------------------------------------------------------------
    punteggio_venditore: Optional[int] = None           # 0-100

    # ------------------------------------------------------------------
    # CAMPI v2.0: stima profitto (vedi profit_calculator.py)
    # ------------------------------------------------------------------
    valore_stimato: Optional[float] = None
    risparmio_euro: Optional[float] = None
    risparmio_percento: Optional[float] = None
    roi_stimato: Optional[float] = None                 # percentuale
    profitto_stimato: Optional[float] = None            # euro, al netto di un margine costi configurabile
    margine_percento: Optional[float] = None


SCHEMA_TABELLE = """
CREATE TABLE IF NOT EXISTS annunci (
    id TEXT PRIMARY KEY,
    piattaforma TEXT NOT NULL,
    titolo TEXT,
    prezzo REAL,
    valuta TEXT,
    marca TEXT,
    taglia TEXT,
    url TEXT,
    foto_url TEXT,
    descrizione TEXT,
    venditore TEXT,
    keyword_trovata TEXT,
    profilo_ricerca TEXT,
    timestamp_trovato TEXT,
    prezzo_medio_mercato REAL,
    is_affare INTEGER,
    punteggio_affidabilita INTEGER,
    motivo_affidabilita TEXT,
    prezzo_offerta_suggerito REAL,
    esito_analisi_foto TEXT,
    notificato INTEGER DEFAULT 0
);

-- Profilo aggregato di un venditore (vedi seller_score.py). Una riga per
-- coppia (piattaforma, venditore): cosi il punteggio si calcola una sola
-- volta e si riusa per tutti gli annunci dello stesso venditore, invece di
-- richiamare l'AI/le euristiche ad ogni singolo annuncio (punto 16,
-- performance/caching).
CREATE TABLE IF NOT EXISTS seller_profiles (
    piattaforma TEXT NOT NULL,
    venditore TEXT NOT NULL,
    punteggio INTEGER,
    feedback_positivi INTEGER,
    feedback_totali INTEGER,
    anzianita_mesi INTEGER,
    numero_articoli INTEGER,
    numero_vendite INTEGER,
    tempo_risposta_ore REAL,
    coerenza_annunci INTEGER,         -- 0-100, quanto gli annunci dello stesso venditore sono internamente coerenti
    calcolato_il TEXT NOT NULL,
    PRIMARY KEY (piattaforma, venditore)
);

-- ----------------------------------------------------------------------
-- TABELLE PER IL BOT TELEGRAM INTERATTIVO
-- ----------------------------------------------------------------------

-- Preferiti: l'utente puo salvare una keyword da ricontrollare periodicamente
-- oppure un singolo annuncio specifico (uno dei due campi e valorizzato).
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    tipo TEXT NOT NULL,              -- "keyword" oppure "annuncio"
    keyword TEXT,                    -- valorizzato se tipo = "keyword"
    annuncio_id TEXT,                -- valorizzato se tipo = "annuncio" (FK logica verso annunci.id)
    creato_il TEXT NOT NULL
);

-- Cronologia delle ricerche libere fatte via Telegram (testo scritto dall'utente)
CREATE TABLE IF NOT EXISTS telegram_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    query TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    risultati_trovati INTEGER DEFAULT 0
);

-- Stato per-chat: ricerca corrente, pagina, filtri, ordinamento, annunci gia
-- mostrati. Una sola riga per chat_id (sovrascritta ad ogni aggiornamento).
-- Il campo dati_json contiene un oggetto JSON con tutto lo stato (vedi
-- telegram_state.py) cosi non serve continuare ad alterare lo schema ogni
-- volta che lo stato si arricchisce di nuovi campi.
CREATE TABLE IF NOT EXISTS telegram_sessions (
    chat_id TEXT PRIMARY KEY,
    dati_json TEXT NOT NULL,
    aggiornato_il TEXT NOT NULL
);

-- Annunci che l'utente ha esplicitamente segnato come "visto" da Telegram
-- (bottone "Segna come visto"). Diverso da annunci.notificato, che riguarda
-- solo l'invio automatico delle notifiche Telegram in main.py.
CREATE TABLE IF NOT EXISTS seen_ads (
    chat_id TEXT NOT NULL,
    annuncio_id TEXT NOT NULL,
    visto_il TEXT NOT NULL,
    PRIMARY KEY (chat_id, annuncio_id)
);

-- Annunci/pattern che l'utente ha scelto di nascondere (bottone "Nascondi
-- annunci simili" o "Ignora"). tipo_match determina come viene applicato
-- il filtro nelle ricerche successive.
CREATE TABLE IF NOT EXISTS ignored_ads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    tipo_match TEXT NOT NULL,        -- "annuncio_singolo", "marca", "venditore"
    valore TEXT NOT NULL,            -- annuncio_id, oppure il nome marca/venditore
    creato_il TEXT NOT NULL
);

-- Riferimenti compatti per callback_data Telegram. Telegram limita i dati
-- dei bottoni a 64 byte: alcuni marketplace possono generare ID annuncio
-- molto lunghi, quindi salviamo un ref breve -> id reale.
CREATE TABLE IF NOT EXISTS telegram_callback_refs (
    ref TEXT PRIMARY KEY,
    annuncio_id TEXT NOT NULL,
    creato_il TEXT NOT NULL
);
"""

SCHEMA_INDICI = """
CREATE INDEX IF NOT EXISTS idx_profilo ON annunci(profilo_ricerca);
CREATE INDEX IF NOT EXISTS idx_notificato ON annunci(notificato);
CREATE INDEX IF NOT EXISTS idx_score ON annunci(score_finale);
CREATE INDEX IF NOT EXISTS idx_favorites_chat ON favorites(chat_id);
CREATE INDEX IF NOT EXISTS idx_history_chat ON telegram_history(chat_id);
CREATE INDEX IF NOT EXISTS idx_ignored_chat ON ignored_ads(chat_id);
CREATE INDEX IF NOT EXISTS idx_callback_refs_annuncio ON telegram_callback_refs(annuncio_id);
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migra_se_necessario(conn: sqlite3.Connection) -> None:
    """
    Gestisce la migrazione di database creati con versioni precedenti dello
    schema. CREATE TABLE IF NOT EXISTS non aggiunge colonne mancanti a
    tabelle gia esistenti, quindi serve un controllo esplicito qui per
    restare retrocompatibili senza obbligare l'utente a cancellare il
    database ad ogni aggiornamento.

    Elenco unico di tutte le colonne introdotte dopo lo schema v1.0
    originale, con il loro tipo SQL. Aggiungere qui una riga per ogni nuova
    colonna futura e' sufficiente per restare retrocompatibili.
    """
    colonne_nuove = {
        # v1.x
        "score_finale": "REAL",
        # v2.0 - riconoscimento prodotto (punto 1, 2, 3)
        "modello": "TEXT",
        "categoria": "TEXT",
        "sottocategoria": "TEXT",
        "collezione": "TEXT",
        "edizione": "TEXT",
        "anno": "INTEGER",
        "colore_principale": "TEXT",
        "colori_secondari": "TEXT",
        "materiale": "TEXT",
        "condizione": "TEXT",
        "genere": "TEXT",
        "collaborazioni": "TEXT",
        "limited_edition": "INTEGER",
        "attributi_estratti_il": "TEXT",
        # v2.0 - traduzione (punto 4)
        "lingua_originale": "TEXT",
        "titolo_originale": "TEXT",
        "descrizione_originale": "TEXT",
        "tradotto_il": "TEXT",
        # v2.0 - OCR e analisi immagine avanzata (punto 6, 7)
        "testo_ocr": "TEXT",
        "difetti_rilevati": "TEXT",
        "immagine_sospetta": "INTEGER",
        # v2.0 - punteggio venditore (punto 9)
        "punteggio_venditore": "INTEGER",
        # v2.0 - stima profitto (punto 10)
        "valore_stimato": "REAL",
        "risparmio_euro": "REAL",
        "risparmio_percento": "REAL",
        "roi_stimato": "REAL",
        "profitto_stimato": "REAL",
        "margine_percento": "REAL",
    }

    colonne_esistenti = {row["name"] for row in conn.execute("PRAGMA table_info(annunci)").fetchall()}
    for nome_colonna, tipo_sql in colonne_nuove.items():
        if nome_colonna not in colonne_esistenti:
            conn.execute(f"ALTER TABLE annunci ADD COLUMN {nome_colonna} {tipo_sql}")


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA_TABELLE)
        _migra_se_necessario(conn)
        conn.executescript(SCHEMA_INDICI)


def esiste_annuncio(annuncio_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM annunci WHERE id = ?", (annuncio_id,)).fetchone()
        return row is not None


def salva_annuncio(a: Annuncio) -> None:
    """
    Salva (o sovrascrive) un annuncio nel database. Costruisce la query
    dinamicamente a partire dai campi della dataclass Annuncio invece di
    elencarli manualmente: con ~35 campi (e altri che si aggiungeranno in
    futuro) un INSERT scritto a mano rischia facilmente di disallinearsi
    dalla dataclass. notificato e is_affare richiedono conversione esplicita
    bool->int perche sqlite3 non fa coercion automatica dei bool Python.
    """
    dati = asdict(a)
    dati["is_affare"] = int(a.is_affare) if a.is_affare is not None else None
    dati["notificato"] = int(a.notificato)
    dati["limited_edition"] = int(a.limited_edition) if a.limited_edition is not None else None
    dati["immagine_sospetta"] = int(a.immagine_sospetta) if a.immagine_sospetta is not None else None

    colonne = list(dati.keys())
    placeholders = ", ".join("?" for _ in colonne)
    valori = [dati[c] for c in colonne]

    with get_connection() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO annunci ({', '.join(colonne)}) VALUES ({placeholders})",
            valori,
        )


def aggiorna_campi(annuncio_id: str, **campi) -> None:
    """Aggiorna solo alcuni campi di un annuncio già salvato (es. dopo l'analisi AI)."""
    if not campi:
        return
    set_clause = ", ".join(f"{k} = ?" for k in campi.keys())
    valori = list(campi.values()) + [annuncio_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE annunci SET {set_clause} WHERE id = ?", valori)


def prezzo_medio_per_profilo(profilo_ricerca: str, escludi_id: Optional[str] = None) -> Optional[dict]:
    """
    Calcola media e mediana dei prezzi storici per un profilo di ricerca,
    usando solo annunci con prezzo valido. Ritorna None se non ci sono
    abbastanza campioni.
    """
    with get_connection() as conn:
        query = "SELECT prezzo FROM annunci WHERE profilo_ricerca = ? AND prezzo > 0"
        params = [profilo_ricerca]
        if escludi_id:
            query += " AND id != ?"
            params.append(escludi_id)
        rows = conn.execute(query, params).fetchall()

    prezzi = sorted(r["prezzo"] for r in rows)
    if len(prezzi) < config.MIN_CAMPIONI_PER_MEDIA:
        return None

    n = len(prezzi)
    media = sum(prezzi) / n
    mediana = prezzi[n // 2] if n % 2 == 1 else (prezzi[n // 2 - 1] + prezzi[n // 2]) / 2

    return {
        "media": round(media, 2),
        "mediana": round(mediana, 2),
        "min": prezzi[0],
        "max": prezzi[-1],
        "campioni": n,
    }


def annuncio_da_riga(row: dict) -> Annuncio:
    """
    Ricostruisce un oggetto Annuncio a partire da una riga del database
    (dict). Centralizzata qui perche SQLite ritorna i booleani come interi
    (0/1), non come bool Python - se ogni modulo facesse Annuncio(**row) a
    mano rischierebbe lo stesso bug (confronti tipo "is True" che falliscono
    silenziosamente su un int). Usa sempre questa funzione invece di
    costruire Annuncio direttamente da una riga del database.
    """
    dati = dict(row)
    campi_booleani = ("is_affare", "notificato", "limited_edition", "immagine_sospetta")
    for campo in campi_booleani:
        if campo in dati and dati[campo] is not None:
            dati[campo] = bool(dati[campo])
    return Annuncio(**dati)


def annunci_da_notificare() -> list:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM annunci WHERE notificato = 0 ORDER BY timestamp_trovato").fetchall()
        return [dict(r) for r in rows]


def segna_notificato(annuncio_id: str) -> None:
    aggiorna_campi(annuncio_id, notificato=1)


def annunci_per_score(profilo_ricerca: Optional[str] = None, limite: Optional[int] = None) -> list[dict]:
    """
    Ritorna gli annunci ordinati per score_finale decrescente (i migliori
    prima). Usata sia da main.py per scegliere gli "affari eccellenti" da
    notificare automaticamente, sia dal bot interattivo per il ranking.
    """
    query = "SELECT * FROM annunci WHERE score_finale IS NOT NULL"
    params = []
    if profilo_ricerca:
        query += " AND profilo_ricerca = ?"
        params.append(profilo_ricerca)
    query += " ORDER BY score_finale DESC"
    if limite:
        query += " LIMIT ?"
        params.append(limite)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def annunci_per_id(annuncio_ids: list[str]) -> list[dict]:
    """Ritorna gli annunci corrispondenti a una lista di ID, nello stesso ordine se possibile."""
    if not annuncio_ids:
        return []
    placeholders = ",".join("?" for _ in annuncio_ids)
    with get_connection() as conn:
        rows = conn.execute(f"SELECT * FROM annunci WHERE id IN ({placeholders})", annuncio_ids).fetchall()
    diz = {r["id"]: dict(r) for r in rows}
    return [diz[i] for i in annuncio_ids if i in diz]


# ----------------------------------------------------------------------------
# PROFILO VENDITORE (seller_profiles) - vedi seller_score.py
# ----------------------------------------------------------------------------

def carica_profilo_venditore(piattaforma: str, venditore: str) -> Optional[dict]:
    """
    Ritorna il profilo venditore gia calcolato e salvato, o None se non
    ancora presente. Centralizza qui la cache per non dover ricalcolare lo
    score venditore per ogni annuncio dello stesso venditore (punto 16,
    performance/caching).
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM seller_profiles WHERE piattaforma = ? AND venditore = ?",
            (piattaforma, venditore),
        ).fetchone()
    return dict(row) if row else None


def salva_profilo_venditore(piattaforma: str, venditore: str, dati: dict) -> None:
    """
    Salva (o sovrascrive) il profilo calcolato di un venditore. dati deve
    contenere le chiavi corrispondenti alle colonne di seller_profiles
    (punteggio, feedback_positivi, ecc.) - le chiavi mancanti vengono
    salvate come NULL.
    """
    colonne_attese = [
        "punteggio", "feedback_positivi", "feedback_totali", "anzianita_mesi",
        "numero_articoli", "numero_vendite", "tempo_risposta_ore", "coerenza_annunci",
    ]
    valori = {c: dati.get(c) for c in colonne_attese}
    valori["piattaforma"] = piattaforma
    valori["venditore"] = venditore
    valori["calcolato_il"] = datetime.now().isoformat(timespec="seconds")

    colonne = list(valori.keys())
    placeholders = ", ".join("?" for _ in colonne)
    with get_connection() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO seller_profiles ({', '.join(colonne)}) VALUES ({placeholders})",
            [valori[c] for c in colonne],
        )


def profilo_venditore_e_recente(profilo: dict, giorni_validita: int) -> bool:
    """
    Determina se un profilo venditore salvato e' ancora abbastanza recente
    da poter essere riusato senza ricalcolo (punto 16, caching). Centralizza
    qui questo controllo cosi seller_score.py non deve duplicare il parsing
    delle date.
    """
    if not profilo or not profilo.get("calcolato_il"):
        return False
    try:
        calcolato_il = datetime.fromisoformat(profilo["calcolato_il"])
    except ValueError:
        return False
    return (datetime.now() - calcolato_il).days < giorni_validita


# ----------------------------------------------------------------------------
# PREFERITI (favorites)
# ----------------------------------------------------------------------------

def aggiungi_preferito_keyword(chat_id: str, keyword: str) -> None:
    """Salva una keyword tra i preferiti di una chat, per poterla ricontrollare in seguito."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO favorites (chat_id, tipo, keyword, creato_il) VALUES (?, 'keyword', ?, ?)",
            (chat_id, keyword, datetime.now().isoformat(timespec="seconds")),
        )


def aggiungi_preferito_annuncio(chat_id: str, annuncio_id: str) -> None:
    """Salva un singolo annuncio tra i preferiti di una chat."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO favorites (chat_id, tipo, annuncio_id, creato_il) VALUES (?, 'annuncio', ?, ?)",
            (chat_id, annuncio_id, datetime.now().isoformat(timespec="seconds")),
        )


def lista_preferiti(chat_id: str) -> list[dict]:
    """Ritorna tutti i preferiti (keyword e annunci) di una chat, piu recenti prima."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM favorites WHERE chat_id = ? ORDER BY creato_il DESC", (chat_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def rimuovi_preferito(chat_id: str, preferito_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM favorites WHERE chat_id = ? AND id = ?", (chat_id, preferito_id))


# ----------------------------------------------------------------------------
# CRONOLOGIA RICERCHE TELEGRAM (telegram_history)
# ----------------------------------------------------------------------------

def salva_ricerca_cronologia(chat_id: str, query_testo: str, risultati_trovati: int) -> None:
    """Registra una ricerca libera fatta da un utente via Telegram."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO telegram_history (chat_id, query, timestamp, risultati_trovati) VALUES (?, ?, ?, ?)",
            (chat_id, query_testo, datetime.now().isoformat(timespec="seconds"), risultati_trovati),
        )


def lista_cronologia(chat_id: str, limite: int = 10) -> list[dict]:
    """Ritorna le ultime ricerche fatte da una chat, piu recenti prima."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM telegram_history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?",
            (chat_id, limite),
        ).fetchall()
    return [dict(r) for r in rows]


# ----------------------------------------------------------------------------
# STATO SESSIONE PER CHAT (telegram_sessions)
# ----------------------------------------------------------------------------

def salva_sessione(chat_id: str, dati_json: str) -> None:
    """
    Salva (o sovrascrive) lo stato corrente di una chat. dati_json è una
    stringa JSON già serializzata - la serializzazione/deserializzazione
    vera e propria vive in telegram_state.py, qui c'è solo la persistenza.
    """
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO telegram_sessions (chat_id, dati_json, aggiornato_il)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET dati_json = excluded.dati_json, aggiornato_il = excluded.aggiornato_il
            """,
            (chat_id, dati_json, datetime.now().isoformat(timespec="seconds")),
        )


def carica_sessione(chat_id: str) -> Optional[str]:
    """Ritorna la stringa JSON dello stato salvato per una chat, o None se non esiste."""
    with get_connection() as conn:
        row = conn.execute("SELECT dati_json FROM telegram_sessions WHERE chat_id = ?", (chat_id,)).fetchone()
    return row["dati_json"] if row else None


# ----------------------------------------------------------------------------
# ANNUNCI VISTI (seen_ads) E IGNORATI (ignored_ads)
# ----------------------------------------------------------------------------

def segna_visto(chat_id: str, annuncio_id: str) -> None:
    """Segna un annuncio come visto da una specifica chat (bottone 'Segna come visto')."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_ads (chat_id, annuncio_id, visto_il) VALUES (?, ?, ?)",
            (chat_id, annuncio_id, datetime.now().isoformat(timespec="seconds")),
        )


def annunci_visti(chat_id: str) -> set:
    """Ritorna l'insieme degli ID annuncio già visti da una chat."""
    with get_connection() as conn:
        rows = conn.execute("SELECT annuncio_id FROM seen_ads WHERE chat_id = ?", (chat_id,)).fetchall()
    return {r["annuncio_id"] for r in rows}


def ignora_pattern(chat_id: str, tipo_match: str, valore: str) -> None:
    """
    Registra un pattern da ignorare per una chat. tipo_match puo essere:
    - "annuncio_singolo": ignora solo quell'annuncio specifico (bottone "Ignora")
    - "marca": ignora tutti gli annunci di quella marca (bottone "Nascondi annunci simili")
    - "venditore": ignora tutti gli annunci di quel venditore
    """
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO ignored_ads (chat_id, tipo_match, valore, creato_il) VALUES (?, ?, ?, ?)",
            (chat_id, tipo_match, valore, datetime.now().isoformat(timespec="seconds")),
        )


def pattern_ignorati(chat_id: str) -> list[dict]:
    """Ritorna tutti i pattern ignorati da una chat."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM ignored_ads WHERE chat_id = ?", (chat_id,)).fetchall()
    return [dict(r) for r in rows]


def filtra_ignorati(chat_id: str, annunci: list[dict]) -> list[dict]:
    """
    Filtra una lista di annunci (dict) rimuovendo quelli che corrispondono a
    un pattern ignorato dalla chat (annuncio singolo, marca, o venditore).
    Centralizzata qui cosi sia il bot interattivo sia eventuali future
    integrazioni usano sempre la stessa logica di esclusione.
    """
    pattern = pattern_ignorati(chat_id)
    if not pattern:
        return annunci

    id_ignorati = {p["valore"] for p in pattern if p["tipo_match"] == "annuncio_singolo"}
    marche_ignorate = {p["valore"].lower() for p in pattern if p["tipo_match"] == "marca"}
    venditori_ignorati = {p["valore"].lower() for p in pattern if p["tipo_match"] == "venditore"}

    risultato = []
    for a in annunci:
        if a.get("id") in id_ignorati:
            continue
        if a.get("marca") and a["marca"].lower() in marche_ignorate:
            continue
        if a.get("venditore") and a["venditore"].lower() in venditori_ignorati:
            continue
        risultato.append(a)
    return risultato


# ----------------------------------------------------------------------------
# RIFERIMENTI CALLBACK TELEGRAM
# ----------------------------------------------------------------------------

def salva_callback_ref(ref: str, annuncio_id: str) -> None:
    """Salva un riferimento breve usato nei callback Telegram."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO telegram_callback_refs (ref, annuncio_id, creato_il)
            VALUES (?, ?, ?)
            """,
            (ref, annuncio_id, datetime.now().isoformat(timespec="seconds")),
        )


def risolvi_callback_ref(ref_o_id: str) -> str:
    """
    Converte un ref compatto Telegram nell'ID annuncio reale. Se non e' un
    ref compatto, ritorna il valore invariato per retrocompatibilita'.
    """
    if not ref_o_id or not ref_o_id.startswith("ref_"):
        return ref_o_id
    with get_connection() as conn:
        row = conn.execute(
            "SELECT annuncio_id FROM telegram_callback_refs WHERE ref = ?",
            (ref_o_id,),
        ).fetchone()
    return row["annuncio_id"] if row else ref_o_id
