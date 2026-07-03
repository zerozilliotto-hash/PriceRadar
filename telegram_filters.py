"""
Applicazione di filtri rapidi (prezzo, taglia, marketplace, marca) e
ordinamento a una lista di ID annuncio, secondo lo stato salvato nella
sessione di una chat Telegram (vedi telegram_state.py).

Centralizzato qui per evitare di duplicare la logica di filtro/ordinamento
sia nella paginazione (telegram_pagination.py) sia nei comandi diretti
(telegram_handlers.py).
"""

from typing import TYPE_CHECKING

import database

if TYPE_CHECKING:
    from telegram_state import FiltriRicerca


def applica_filtri(annuncio_ids: list, filtri: "FiltriRicerca", ordinamento: str) -> list:
    """
    Filtra e ordina una lista di ID annuncio secondo i filtri e
    l'ordinamento correnti. Ritorna una nuova lista di ID (l'ordine
    originale di annuncio_ids non viene modificato in place).

    NOTA SULLA CACHE (punto 11 della richiesta): questa funzione lavora
    sempre sui dati gia presenti nel database (recuperati una sola volta
    dalla ricerca originale) - non viene mai rifatto scraping qui. Solo il
    bottone "Aggiorna ricerca" (vedi telegram_search.py) esegue una nuova
    ricerca sui marketplace.
    """
    if not annuncio_ids:
        return []

    annunci = database.annunci_per_id(annuncio_ids)

    if filtri.prezzo_max is not None:
        annunci = [a for a in annunci if a["prezzo"] is not None and a["prezzo"] <= filtri.prezzo_max]
    if filtri.taglia:
        annunci = [a for a in annunci if a.get("taglia") and a["taglia"].lower() == filtri.taglia.lower()]
    if filtri.marketplace:
        annunci = [a for a in annunci if a["piattaforma"] == filtri.marketplace]
    if filtri.marca:
        annunci = [a for a in annunci if a.get("marca") and a["marca"].lower() == filtri.marca.lower()]
    if getattr(filtri, "colore", None):
        colore = filtri.colore.lower()
        annunci = [
            a for a in annunci
            if colore in " ".join(
                str(a.get(campo) or "").lower()
                for campo in ("colore_principale", "colori_secondari", "titolo", "descrizione")
            )
        ]

    chiavi_ordinamento = {
        "score": lambda a: a.get("score_finale") or 0,
        "prezzo": lambda a: a.get("prezzo") or float("inf"),
        "recente": lambda a: a.get("timestamp_trovato") or "",
        "affidabilita": lambda a: a.get("punteggio_affidabilita") or 0,
    }
    chiave = chiavi_ordinamento.get(ordinamento, chiavi_ordinamento["score"])
    decrescente = ordinamento != "prezzo"  # il prezzo si ordina crescente (piu economico prima), il resto decrescente
    annunci_ordinati = sorted(annunci, key=chiave, reverse=decrescente)

    return [a["id"] for a in annunci_ordinati]


def descrizione_filtri_attivi(filtri: "FiltriRicerca") -> str:
    """Ritorna una stringa leggibile dei filtri attualmente attivi, per mostrarla all'utente."""
    parti = []
    if filtri.prezzo_max is not None:
        parti.append(f"prezzo ≤ {filtri.prezzo_max}€")
    if filtri.taglia:
        parti.append(f"taglia {filtri.taglia}")
    if filtri.marketplace:
        parti.append(f"solo {filtri.marketplace}")
    if filtri.marca:
        parti.append(f"marca {filtri.marca}")
    if getattr(filtri, "colore", None):
        parti.append(f"colore {filtri.colore}")
    return ", ".join(parti) if parti else "nessuno"
