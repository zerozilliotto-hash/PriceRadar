"""
Valutazione del venditore e calcolo dello score (punto 9 della richiesta
v2.0). Lo score venditore diventa una delle componenti del ranking finale
(vedi ranking.py, componente "venditore").

FONTI DATI:
- Vinted/eBay/Depop/Subito non espongono un'API strutturata per i dati
  del profilo venditore accessibile senza autenticazione. Quello che e'
  disponibile nei risultati di ricerca e' spesso limitato a username e
  (a volte) numero di feedback/valutazione media.
- Per questa ragione, lo score venditore e' calcolato su una combinazione
  di: dati estratti dall'annuncio stesso (venditore presente/assente),
  analisi euristica della coerenza degli annunci dello stesso venditore nel
  nostro database, e (quando disponibili) eventuali metadati estratti dalla
  pagina prodotto.

CACHING (punto 16): lo score viene calcolato una volta e salvato in
seller_profiles (vedi database.py). Se lo stesso venditore compare su piu'
annunci, il punteggio viene riusato senza ricalcolo finche' e' recente
(< config.GIORNI_VALIDITA_PROFILO_VENDITORE).

DESIGN MODULARE: questo modulo non dipende da nessun client esterno
specifico (Vinted/eBay/ecc.) - riceve in input i dati gia' estratti
dall'annuncio, cosi se in futuro i client arricchiranno i dati del
venditore, lo score si aggiorna automaticamente.
"""

from datetime import datetime
from typing import Optional

import config
import database


def _calcola_score_da_componenti(componenti: dict) -> int:
    """
    Calcola lo score venditore 0-100 combinando le componenti secondo i pesi
    di config.PESI_SCORE_VENDITORE. Ogni componente e' normalizzata a 0-100
    prima di essere pesata.
    """
    pesi = config.PESI_SCORE_VENDITORE

    # feedback: rapporto positivi/totali * 100, o 50 (neutro) se non disponibile
    if componenti.get("feedback_totali", 0) > 0:
        feedback_score = (componenti["feedback_positivi"] / componenti["feedback_totali"]) * 100
    else:
        feedback_score = 50.0

    # anzianita': piu' mesi = piu' affidabile, con un cap a 24 mesi (2 anni = punteggio pieno)
    anzianita_mesi = componenti.get("anzianita_mesi", 0) or 0
    anzianita_score = min(100, (anzianita_mesi / 24) * 100)

    # volume vendite: log scale fino a 100 vendite = punteggio pieno
    numero_vendite = componenti.get("numero_vendite", 0) or 0
    volume_score = min(100, (numero_vendite / 100) * 100) if numero_vendite > 0 else 30.0

    # tempo risposta: meno ore = meglio. 0h = 100, 24h = 50, 72h+ = 0
    ore_risposta = componenti.get("tempo_risposta_ore")
    if ore_risposta is not None:
        risposta_score = max(0, 100 - (ore_risposta / 72) * 100)
    else:
        risposta_score = 50.0  # neutro se non disponibile

    # coerenza annunci: gia normalizzata 0-100 da _calcola_coerenza_annunci
    coerenza_score = componenti.get("coerenza_annunci", 50) or 50

    score = (
        feedback_score * pesi["feedback"]
        + anzianita_score * pesi["anzianita"]
        + volume_score * pesi["volume_vendite"]
        + risposta_score * pesi["tempo_risposta"]
        + coerenza_score * pesi["coerenza_annunci"]
    )
    return round(max(0, min(100, score)))


def _calcola_coerenza_annunci(piattaforma: str, venditore: str) -> int:
    """
    Misura quanto gli annunci dello stesso venditore nel nostro database
    sono coerenti tra loro: un venditore che vende sempre la stessa categoria
    di prodotto e' piu' specializzato e tendenzialmente piu' affidabile di
    uno che vende tutto e il contrario di tutto.

    Ritorna un punteggio 0-100. Non richiede API esterne: lavora solo sui
    dati gia' nel nostro database.
    """
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT categoria, marca FROM annunci WHERE piattaforma = ? AND venditore = ? AND categoria IS NOT NULL",
            (piattaforma, venditore),
        ).fetchall()

    if not rows:
        return 50  # nessun dato: valore neutro

    categorie = [r["categoria"] for r in rows if r["categoria"]]
    if not categorie:
        return 50

    # Concentrazione: se il 70%+ degli annunci e' nella stessa categoria,
    # coerenza alta. Se completamente dispersi, coerenza bassa.
    categoria_piu_comune = max(set(categorie), key=categorie.count)
    concentrazione = categorie.count(categoria_piu_comune) / len(categorie)

    # Mappa 0.33 (distribuzione uniforme su 3 categorie) -> 0, 1.0 -> 100
    score = max(0, min(100, (concentrazione - 0.33) / 0.67 * 100))
    return round(score)


def calcola_score_venditore(
    piattaforma: str,
    venditore: str,
    dati_extra: Optional[dict] = None,
    forza_ricalcolo: bool = False,
) -> int:
    """
    Calcola (o recupera dalla cache) lo score del venditore 0-100.

    dati_extra puo contenere metadati estratti dai client (es. feedback
    count se disponibile nel payload dell'API). Se non disponibili, si
    usa solo la coerenza degli annunci nel database + valori neutri per
    le componenti mancanti.

    Caching (punto 16): il profilo viene salvato in seller_profiles e
    riusato per tutti gli annunci dello stesso venditore senza ricalcolo,
    finche' e' recente (< config.GIORNI_VALIDITA_PROFILO_VENDITORE giorni).
    """
    if not config.ABILITA_SCORE_VENDITORE or not venditore:
        return 50  # neutro se disattivato o venditore assente

    # Controlla cache
    profilo_esistente = database.carica_profilo_venditore(piattaforma, venditore)
    if profilo_esistente and not forza_ricalcolo:
        if database.profilo_venditore_e_recente(profilo_esistente, config.GIORNI_VALIDITA_PROFILO_VENDITORE):
            return profilo_esistente.get("punteggio") or 50

    # Calcola coerenza annunci (non richiede API esterne)
    coerenza = _calcola_coerenza_annunci(piattaforma, venditore)

    # Inizia con i dati extra se disponibili (es. dall'API eBay)
    componenti = {
        "feedback_positivi": (dati_extra or {}).get("feedback_positivi", 0),
        "feedback_totali": (dati_extra or {}).get("feedback_totali", 0),
        "anzianita_mesi": (dati_extra or {}).get("anzianita_mesi", 0),
        "numero_vendite": (dati_extra or {}).get("numero_vendite", 0),
        "tempo_risposta_ore": (dati_extra or {}).get("tempo_risposta_ore"),
        "coerenza_annunci": coerenza,
    }

    punteggio = _calcola_score_da_componenti(componenti)

    # Salva in cache
    database.salva_profilo_venditore(piattaforma, venditore, {
        "punteggio": punteggio, **componenti
    })

    return punteggio
