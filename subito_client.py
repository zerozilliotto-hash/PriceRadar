"""
Client di ricerca su Subito.it.

Come Depop, Subito.it non ha un'API pubblica per sviluppatori indie, ma le
sue protezioni anti-bot sono relativamente leggere rispetto a Vinted: una
richiesta HTTP diretta con header realistici funziona nella maggior parte
dei casi.

Subito.it accetta parametri di ricerca direttamente nell'URL (q, minPrice,
maxPrice), e incorpora anch'esso dati JSON-LD strutturati nella pagina dei
risultati - usiamo la stessa tecnica del client Depop.

USO PERSONALE SOLO. Rispetta il rate limit (vedi config.py). Anche Subito.it
proibisce lo scraping nei suoi Termini di Servizio.
"""

import json
import re
from typing import Optional
from urllib.parse import quote

import httpx

import config
from database import Annuncio


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}

SUBITO_SEARCH_URL = "https://www.subito.it/annunci-italia/vendita/usato/?q={query}"


def _estrai_dati_strutturati(html: str) -> list[dict]:
    """Estrae i blocchi JSON-LD di tipo Product dalla pagina, come per Depop."""
    blocchi = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    prodotti = []
    for blocco in blocchi:
        try:
            dati = json.loads(blocco)
        except json.JSONDecodeError:
            continue

        elementi = dati if isinstance(dati, list) else [dati]
        for el in elementi:
            if isinstance(el, dict) and el.get("@type") == "Product":
                prodotti.append(el)
            if isinstance(el, dict) and "itemListElement" in el:
                for item in el["itemListElement"]:
                    prodotto = item.get("item") if isinstance(item, dict) else None
                    if isinstance(prodotto, dict):
                        prodotti.append(prodotto)
    return prodotti


def cerca(
    keyword: str,
    prezzo_max: Optional[float],
    profilo_nome: str,
    prezzo_min: Optional[float] = None,
) -> list[Annuncio]:
    """
    Esegue una ricerca su Subito.it per una keyword. Ritorna lista vuota in
    caso di errore, senza interrompere il programma.

    NOTA: come per Depop, questo parsing dipende dal formato della pagina al
    momento della scrittura - se Subito cambia struttura, va aggiornato.
    """
    url = SUBITO_SEARCH_URL.format(query=quote(keyword))
    params = {}
    if prezzo_min is not None:
        params["ps"] = str(int(prezzo_min))
    if prezzo_max is not None:
        params["pe"] = str(int(prezzo_max))

    try:
        resp = httpx.get(url, headers=HEADERS, params=params, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [WARN] [Subito] Errore nella richiesta per '{keyword}': {type(e).__name__} - {e}")
        return []

    prodotti = _estrai_dati_strutturati(resp.text)
    if not prodotti:
        print(f"  [WARN] [Subito] Nessun dato strutturato trovato per '{keyword}' "
              f"(possibile cambiamento del formato pagina o blocco anti-bot)")
        return []

    risultati = []
    for p in prodotti:
        try:
            offerta = p.get("offers", {})
            if isinstance(offerta, list):
                offerta = offerta[0] if offerta else {}
            prezzo = float(offerta.get("price", 0) or 0)
        except (ValueError, TypeError):
            prezzo = 0.0

        immagine = p.get("image")
        if isinstance(immagine, list):
            immagine = immagine[0] if immagine else None

        risultati.append(
            Annuncio(
                id=f"subito_{p.get('sku') or p.get('url', '')}",
                piattaforma="subito",
                titolo=p.get("name", "N/D"),
                prezzo=prezzo,
                valuta=offerta.get("priceCurrency", "EUR"),
                marca=(p.get("brand") or {}).get("name") if isinstance(p.get("brand"), dict) else p.get("brand"),
                taglia=None,
                url=p.get("url", ""),
                foto_url=immagine,
                descrizione=p.get("description"),
                venditore=None,  # Subito spesso mette il venditore solo nella pagina di dettaglio, non in lista
                keyword_trovata=keyword,
                profilo_ricerca=profilo_nome,
            )
        )
    return risultati
