"""
Funzioni che usano un modello Claude per due compiti:

1. Valutare l'affidabilità complessiva di un annuncio (combinando descrizione,
   prezzo, segnali sospetti già rilevati) - dando un punteggio e una
   spiegazione testuale.
2. Suggerire un prezzo ragionevole da offrire al venditore, basandosi sul
   prezzo richiesto e sul prezzo medio di mercato storico.

Richiede ANTHROPIC_API_KEY in .env. Se non configurata, le funzioni
ritornano None senza generare errori, così il resto del programma continua
a funzionare anche senza questa parte.
"""

import json
from typing import Optional

import anthropic

import config
from database import Annuncio
from fraud_detector import ValutazioneSospetto


_client: Optional[anthropic.Anthropic] = None


def _get_client() -> Optional[anthropic.Anthropic]:
    global _client
    if not config.ANTHROPIC_API_KEY:
        return None
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def valuta_affidabilita(annuncio: Annuncio, segnali: ValutazioneSospetto) -> Optional[dict]:
    """
    Ritorna un dict {"punteggio": int 0-100, "motivo": str} oppure None se
    l'AI non è configurata o la chiamata fallisce.

    Punteggio alto = annuncio sembra affidabile. Punteggio basso = attenzione.
    """
    client = _get_client()
    if client is None:
        return None

    prompt = f"""Valuta l'affidabilità di questo annuncio Vinted/eBay, in base SOLO alle informazioni testuali fornite (non puoi vedere le foto).

Titolo: {annuncio.titolo}
Prezzo: {annuncio.prezzo} {annuncio.valuta}
Marca dichiarata: {annuncio.marca or "non specificata"}
Descrizione: {annuncio.descrizione or "(nessuna descrizione)"}
Venditore: {annuncio.venditore or "sconosciuto"}

Segnali automatici già rilevati (punteggio di rischio 0-100, più alto = più sospetto):
{segnali.punteggio_rischio}/100
Motivi: {"; ".join(segnali.motivi) if segnali.motivi else "nessuno"}

Rispondi SOLO con un oggetto JSON, senza markdown, nel formato esatto:
{{"punteggio": <int 0-100, dove 100 = molto affidabile>, "motivo": "<spiegazione breve in italiano, massimo 2 frasi>"}}

Sii equilibrato: non essere eccessivamente sospettoso solo perché il prezzo è basso, ma segnala chiaramente se ci sono incongruenze reali (es. descrizione che contraddice il titolo, richieste di pagamento fuori piattaforma, dettagli mancanti per un prodotto di marca costosa)."""

    try:
        response = client.messages.create(
            model=config.MODELLO_TESTO,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        testo = response.content[0].text.strip()
        testo = testo.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        risultato = json.loads(testo)
        return {
            "punteggio": int(risultato["punteggio"]),
            "motivo": str(risultato["motivo"]),
        }
    except Exception as e:
        print(f"  [WARN] [AI] Errore nella valutazione affidabilità: {type(e).__name__} - {e}")
        return None


def suggerisci_prezzo_offerta(annuncio: Annuncio) -> Optional[float]:
    """
    Suggerisce un prezzo di offerta ragionevole. Usa una logica semplice
    se non c'è AI configurata (sconto fisso del 10%), altrimenti chiede
    al modello un suggerimento più contestuale.
    """
    # Fallback senza AI: sconto fisso del 10%, arrotondato
    fallback = round(annuncio.prezzo * 0.9, 2) if annuncio.prezzo > 0 else None

    client = _get_client()
    if client is None:
        return fallback

    contesto_prezzo_medio = (
        f"Il prezzo medio storico per articoli simili è {annuncio.prezzo_medio_mercato}€."
        if annuncio.prezzo_medio_mercato
        else "Non ci sono ancora dati storici sufficienti sul prezzo medio."
    )

    prompt = f"""Sei un assistente che suggerisce un prezzo ragionevole da OFFRIRE (in trattativa, come acquirente) per un articolo in vendita su un marketplace di seconda mano.

Prezzo richiesto dal venditore: {annuncio.prezzo} {annuncio.valuta}
{contesto_prezzo_medio}
Titolo: {annuncio.titolo}

Regole:
- Suggerisci un prezzo equo, non offensivo per il venditore (uno sconto eccessivo rischia solo di farti ignorare)
- Generalmente uno sconto realistico in trattativa è tra il 5% e il 15% del prezzo richiesto
- Se il prezzo è già molto sotto la media di mercato, suggerisci uno sconto minimo o nessuno sconto

Rispondi SOLO con un numero (il prezzo suggerito in {annuncio.valuta}), senza testo aggiuntivo, es: 45.00"""

    try:
        response = client.messages.create(
            model=config.MODELLO_TESTO,
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}],
        )
        testo = response.content[0].text.strip()
        return round(float(testo.replace(",", ".").replace("€", "").strip()), 2)
    except Exception as e:
        print(f"  [WARN] [AI] Errore nel suggerimento prezzo, uso fallback: {type(e).__name__} - {e}")
        return fallback
