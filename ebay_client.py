"""
Client di ricerca su eBay, usando l'API ufficiale Browse API.

A differenza di Vinted, eBay offre un'API pubblica e legale per chiunque si
registri come developer (gratis): https://developer.ebay.com/

Per usarlo:
1. Registrati su developer.ebay.com
2. Crea una "application" (keyset)
3. Prendi Client ID e Client Secret e metteli nel file .env

L'autenticazione usa OAuth2 con "client credentials" (token applicativo,
non serve login utente per la sola ricerca pubblica).
"""

import time
from typing import Optional

import httpx

import config
from database import Annuncio


_access_token: Optional[str] = None
_token_scadenza: float = 0.0


def _ottieni_token() -> Optional[str]:
    """Richiede (o riusa, se ancora valido) un token OAuth2 applicativo."""
    global _access_token, _token_scadenza

    if _access_token and time.time() < _token_scadenza:
        return _access_token

    if not config.EBAY_CLIENT_ID or not config.EBAY_CLIENT_SECRET:
        return None

    try:
        resp = httpx.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            auth=(config.EBAY_CLIENT_ID, config.EBAY_CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        _access_token = data["access_token"]
        # Rinnova un po' prima della scadenza reale, per sicurezza
        _token_scadenza = time.time() + int(data.get("expires_in", 7200)) - 60
        return _access_token
    except Exception as e:
        print(f"  [WARN] [eBay] Errore nell'autenticazione: {type(e).__name__} - {e}")
        return None


def cerca(keyword: str, prezzo_max: Optional[float], profilo_nome: str) -> list[Annuncio]:
    """
    Esegue una ricerca su eBay per una keyword tramite la Browse API.
    Ritorna lista vuota se le credenziali non sono configurate o se la
    richiesta fallisce.
    """
    token = _ottieni_token()
    if not token:
        return []  # eBay non configurato: nessun errore, semplicemente skip

    params = {"q": keyword, "limit": "50", "sort": "newlyListed"}
    filtri = []
    if prezzo_max is not None:
        filtri.append(f"price:[..{prezzo_max}]")
        filtri.append("priceCurrency:EUR")
    if filtri:
        params["filter"] = ",".join(filtri)

    try:
        resp = httpx.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": config.EBAY_MARKETPLACE,
            },
            params=params,
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [WARN] [eBay] Errore nella ricerca di '{keyword}': {type(e).__name__} - {e}")
        return []

    risultati = []
    for item in data.get("itemSummaries", []):
        prezzo_info = item.get("price", {})
        risultati.append(
            Annuncio(
                id=f"ebay_{item.get('itemId', '')}",
                piattaforma="ebay",
                titolo=item.get("title", "N/D"),
                prezzo=float(prezzo_info.get("value", 0) or 0),
                valuta=prezzo_info.get("currency", "EUR"),
                marca=None,  # la Browse API non da sempre il brand in modo diretto
                taglia=None,
                url=item.get("itemWebUrl", ""),
                foto_url=(item.get("image") or {}).get("imageUrl"),
                descrizione=item.get("shortDescription"),
                venditore=(item.get("seller") or {}).get("username"),
                keyword_trovata=keyword,
                profilo_ricerca=profilo_nome,
            )
        )
    return risultati
