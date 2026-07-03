"""
Stima del profitto e ROI per ogni annuncio (punto 10 della richiesta v2.0).

Mostra:
- Prezzo (prezzo richiesto dal venditore)
- Valore stimato (prezzo medio di mercato calcolato da price_analyzer.py)
- Risparmio € (valore_stimato - prezzo, se positivo)
- Risparmio % (risparmio / valore_stimato * 100)
- ROI stimato % ((valore_stimato - prezzo - costi) / prezzo * 100)
- Profitto stimato € (risparmio - costi forfettari)
- Margine % (profitto / valore_stimato * 100)

I costi forfettari (spedizione, commissioni piattaforma, margine di
rischio) sono configurabili in config.MARGINE_COSTI_PERCENTO.

Richiede che price_analyzer.py abbia gia' calcolato prezzo_medio_mercato
per l'annuncio - quindi viene chiamato dopo price_analyzer, non in
parallelo. Se prezzo_medio_mercato e' None (non abbastanza dati storici),
i valori di profitto/ROI restano None.
"""

from typing import Optional

import config
from database import Annuncio


def calcola_profitto(annuncio: Annuncio) -> Annuncio:
    """
    Calcola e popola tutti i campi di stima profitto dell'annuncio (punto 10).
    Modifica l'annuncio sul posto e lo ritorna.

    Robustezza (punto 17): se prezzo_medio_mercato non e' disponibile, o
    se i valori numerici non sono validi, i campi restano None senza crash.
    """
    if not config.ABILITA_STIMA_PROFITTO:
        return annuncio

    if not annuncio.prezzo_medio_mercato or annuncio.prezzo_medio_mercato <= 0:
        return annuncio  # non abbastanza dati storici per una stima sensata

    if not annuncio.prezzo or annuncio.prezzo <= 0:
        return annuncio

    try:
        prezzo = float(annuncio.prezzo)
        valore = float(annuncio.prezzo_medio_mercato)
        costi = prezzo * (config.MARGINE_COSTI_PERCENTO / 100)

        risparmio_euro = round(valore - prezzo, 2)
        risparmio_percento = round((risparmio_euro / valore) * 100, 1) if valore > 0 else 0.0
        profitto_stimato = round(risparmio_euro - costi, 2)
        roi_stimato = round((profitto_stimato / prezzo) * 100, 1) if prezzo > 0 else 0.0
        margine_percento = round((profitto_stimato / valore) * 100, 1) if valore > 0 else 0.0

        annuncio.valore_stimato = round(valore, 2)
        annuncio.risparmio_euro = risparmio_euro
        annuncio.risparmio_percento = risparmio_percento
        annuncio.profitto_stimato = profitto_stimato
        annuncio.roi_stimato = roi_stimato
        annuncio.margine_percento = margine_percento

    except (TypeError, ZeroDivisionError, ValueError) as e:
        print(f"  [WARN] [Profitto] Errore nel calcolo per '{annuncio.id}': {type(e).__name__} - {e}")

    return annuncio


def riepilogo_profitto(annuncio: Annuncio) -> str:
    """
    Ritorna una stringa leggibile con il riepilogo economico dell'annuncio,
    usata nei messaggi Telegram e nella dashboard (punto 10, 11, 12).
    """
    if annuncio.valore_stimato is None:
        return "💹 Stima profitto: dati di mercato insufficienti"

    valuta = annuncio.valuta or "EUR"
    righe = [f"💹 Analisi economica:"]
    righe.append(f"   Prezzo: {annuncio.prezzo} {valuta}")
    righe.append(f"   Valore stimato: {annuncio.valore_stimato} {valuta}")

    if annuncio.risparmio_euro is not None:
        segno = "+" if annuncio.risparmio_euro > 0 else ""
        righe.append(f"   Risparmio: {segno}{annuncio.risparmio_euro} {valuta} ({annuncio.risparmio_percento}%)")

    if annuncio.profitto_stimato is not None:
        righe.append(f"   Profitto stimato (al netto costi): {annuncio.profitto_stimato} {valuta}")

    if annuncio.roi_stimato is not None:
        emoji = "🟢" if annuncio.roi_stimato > 20 else ("🟡" if annuncio.roi_stimato > 5 else "🔴")
        righe.append(f"   {emoji} ROI: {annuncio.roi_stimato}%")

    return "\n".join(righe)
