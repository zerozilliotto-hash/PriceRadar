"""
Client di ricerca su Vinted.

Vinted non ha un'API pubblica ufficiale: questo modulo usa la libreria
community "vinted-scraper" che si appoggia a un endpoint interno non
documentato. Può rompersi se Vinted aggiorna le proprie protezioni
anti-bot (Datadome) -> in quel caso aggiorna la libreria con
`pip install -U vinted-scraper` o consulta la pagina GitHub del progetto.

USO PERSONALE SOLO. Rispetta il rate limit (vedi config.py).
"""

from typing import Any, Optional

from vinted_scraper import VintedScraper

import config
from database import Annuncio


_scraper: Optional[VintedScraper] = None


def _get_scraper() -> VintedScraper:
    global _scraper
    if _scraper is None:
        _scraper = VintedScraper(config.VINTED_DOMAIN)
    return _scraper


def _get_value(data: Any, key: str, default=None):
    """Legge un valore da oggetti o dizionari ritornati da vinted-scraper."""
    if data is None:
        return default
    if isinstance(data, dict):
        return data.get(key, default)
    return getattr(data, key, default)


def _estrai_url_foto(item: Any) -> Optional[str]:
    """
    vinted-scraper puo restituire la foto principale come dict o come oggetto,
    a seconda della versione e dell'endpoint. Preferiamo l'immagine full-size
    quando disponibile, con fallback all'URL standard.
    """
    foto = _get_value(item, "photo")
    url = _get_value(foto, "full_size_url") or _get_value(foto, "url")
    if url:
        return url

    foto_lista = _get_value(item, "photos") or []
    for foto in foto_lista:
        url = _get_value(foto, "full_size_url") or _get_value(foto, "url")
        if url:
            return url
    return None


def cerca(keyword: str, prezzo_max: Optional[float], profilo_nome: str) -> list[Annuncio]:
    """
    Esegue una ricerca su Vinted per una keyword e ritorna una lista di
    oggetti Annuncio. In caso di errore (es. 403 da Datadome, sia
    nell'inizializzazione dello scraper sia nella ricerca vera e propria),
    ritorna una lista vuota e stampa un avviso, senza interrompere il
    programma chiamante.
    """
    global _scraper

    try:
        scraper = _get_scraper()
        params = {"search_text": keyword, "order": "newest_first"}
        if prezzo_max is not None:
            params["price_to"] = prezzo_max
        items = scraper.search(params)
    except Exception as e:
        print(f"  [WARN] [Vinted] Errore nella ricerca di '{keyword}': {type(e).__name__} - {e}")
        # Se l'errore arriva dall'inizializzazione dello scraper (es. cookie
        # di sessione scaduto/rifiutato), azzeriamo la cache cosi il
        # prossimo tentativo ne crea uno nuovo invece di ripetere sempre lo
        # stesso fallimento con un oggetto scraper "rotto"
        _scraper = None
        return []

    risultati = []
    for item in items:
        risultati.append(
            Annuncio(
                id=f"vinted_{getattr(item, 'id', '')}",
                piattaforma="vinted",
                titolo=getattr(item, "title", "N/D"),
                prezzo=float(getattr(item, "price", 0) or 0),
                valuta=getattr(item, "currency", "EUR"),
                marca=getattr(item, "brand_title", None),
                taglia=getattr(item, "size_title", None),
                url=getattr(item, "url", ""),
                foto_url=_estrai_url_foto(item),
                descrizione=getattr(item, "description", None),
                venditore=getattr(getattr(item, "user", None), "login", None) if hasattr(item, "user") else None,
                keyword_trovata=keyword,
                profilo_ricerca=profilo_nome,
                condizione=getattr(item, "status", None),
                colore_principale=getattr(item, "color1", None),
            )
        )
    return risultati
