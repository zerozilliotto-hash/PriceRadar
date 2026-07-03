"""
Client di ricerca su Depop.

Depop non ha un'API pubblica ufficiale per sviluppatori indie. A differenza
di Vinted (che ha Datadome, protezione pesante), Depop usa Cloudflare con
protezione più leggera: richieste HTTP dirette con header realistici
funzionano nella maggior parte dei casi, senza bisogno di librerie
specializzate.

Tecnica usata: Depop incorpora i risultati di ricerca come dati JSON-LD
strutturati (schema.org) dentro la pagina HTML, oltre ai dati visivi. Questo
è più stabile del parsing dei tag HTML/CSS, perché il markup visivo cambia
più spesso del formato dei dati strutturati.

USO PERSONALE SOLO. Rispetta il rate limit (vedi config.py). Depop, come
Vinted, proibisce lo scraping nei suoi Termini di Servizio.
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

DEPOP_SEARCH_URL = "https://www.depop.com/search/?q={query}"


def _estrai_dati_strutturati(html: str) -> list[dict]:
    """
    Cerca i blocchi <script type="application/ld+json"> nella pagina e
    ritorna la lista di prodotti trovati. Depop, come molti siti e-commerce,
    usa questo formato per la SEO - è più stabile da fare parsing rispetto
    alle classi CSS, che cambiano più di frequente.
    """
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
            # Alcuni siti annidano i prodotti in itemListElement
            if isinstance(el, dict) and "itemListElement" in el:
                for item in el["itemListElement"]:
                    prodotto = item.get("item") if isinstance(item, dict) else None
                    if isinstance(prodotto, dict):
                        prodotti.append(prodotto)
    return prodotti


def cerca(keyword: str, prezzo_max: Optional[float], profilo_nome: str) -> list[Annuncio]:
    """
    Esegue una ricerca su Depop per una keyword. Ritorna lista vuota in caso
    di errore (rete, blocco anti-bot, formato pagina cambiato), senza
    interrompere il programma.

    NOTA: questo parsing dipende dal formato della pagina Depop al momento
    della scrittura. Se Depop cambia struttura, questa funzione potrebbe
    ritornare 0 risultati anche se la ricerca avrebbe risultati validi -
    in tal caso va aggiornato il parsing.
    """
    url = DEPOP_SEARCH_URL.format(query=quote(keyword))

    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [WARN] [Depop] Errore nella richiesta per '{keyword}': {type(e).__name__} - {e}")
        return []

    prodotti = _estrai_dati_strutturati(resp.text)
    if not prodotti:
        print(f"  [WARN] [Depop] Nessun dato strutturato trovato per '{keyword}' "
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

        if prezzo_max is not None and prezzo > prezzo_max:
            continue

        immagine = p.get("image")
        if isinstance(immagine, list):
            immagine = immagine[0] if immagine else None

        risultati.append(
            Annuncio(
                id=f"depop_{p.get('sku') or p.get('productID') or p.get('url', '')}",
                piattaforma="depop",
                titolo=p.get("name", "N/D"),
                prezzo=prezzo,
                valuta=offerta.get("priceCurrency", "EUR"),
                marca=(p.get("brand") or {}).get("name") if isinstance(p.get("brand"), dict) else p.get("brand"),
                taglia=None,  # spesso non presente nei dati strutturati di ricerca, solo nella pagina prodotto
                url=p.get("url", ""),
                foto_url=immagine,
                descrizione=p.get("description"),
                venditore=(offerta.get("seller") or {}).get("name") if isinstance(offerta.get("seller"), dict) else None,
                keyword_trovata=keyword,
                profilo_ricerca=profilo_nome,
            )
        )
    return risultati
