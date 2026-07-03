"""
Gestione dei preferiti (punto 7 della richiesta): l'utente puo salvare una
keyword da ricontrollare periodicamente, oppure un singolo annuncio.

"Controlla preferiti" esegue la ricerca solo sulle keyword salvate, usando
la stessa pipeline temporanea di telegram_search.py (niente duplicazione di
logica di scraping/analisi).
"""

import database
import telegram_search


def aggiungi_keyword_ai_preferiti(chat_id: str, keyword: str) -> None:
    """Salva una keyword tra i preferiti di una chat."""
    database.aggiungi_preferito_keyword(str(chat_id), keyword)


def aggiungi_annuncio_ai_preferiti(chat_id: str, annuncio_id: str) -> None:
    """Salva un singolo annuncio tra i preferiti di una chat."""
    database.aggiungi_preferito_annuncio(str(chat_id), annuncio_id)


def rimuovi_dai_preferiti(chat_id: str, preferito_id: int) -> None:
    database.rimuovi_preferito(str(chat_id), preferito_id)


def elenco_preferiti(chat_id: str) -> list:
    """Ritorna tutti i preferiti di una chat, gia pronti per essere mostrati."""
    return database.lista_preferiti(str(chat_id))


def controlla_tutti_i_preferiti(chat_id: str) -> dict:
    """
    Esegue la ricerca per ogni keyword salvata nei preferiti di una chat, e
    raccoglie lo stato aggiornato di ogni annuncio preferito singolo.

    Ritorna un dizionario:
    {
        "per_keyword": {"nike tech fleece": [id1, id2, ...], ...},
        "annunci_preferiti_aggiornati": [dict, dict, ...],
    }

    Riusa telegram_search.esegui_ricerca_libera, quindi anche questi
    controlli passano dalla stessa pipeline di analisi (prezzo, fraud, AI,
    score) usata ovunque nel sistema - nessuna logica duplicata.
    """
    preferiti = elenco_preferiti(chat_id)
    keyword_preferite = [p["keyword"] for p in preferiti if p["tipo"] == "keyword" and p["keyword"]]
    annunci_preferiti_ids = [p["annuncio_id"] for p in preferiti if p["tipo"] == "annuncio" and p["annuncio_id"]]

    risultati_per_keyword = {}
    for kw in keyword_preferite:
        risultati_per_keyword[kw] = telegram_search.esegui_ricerca_libera_semplice(kw)

    annunci_aggiornati = database.annunci_per_id(annunci_preferiti_ids)

    return {
        "per_keyword": risultati_per_keyword,
        "annunci_preferiti_aggiornati": annunci_aggiornati,
    }
