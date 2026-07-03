"""
Calcolo dello score finale di un annuncio, combinando piu segnali in un
unico numero usato per ordinare e classificare gli annunci ovunque nel
sistema (notifiche automatiche, bot interattivo, dashboard).

Perche centralizzare qui: prima dell'introduzione di questo modulo, ogni
parte del sistema decideva "cosa e un buon annuncio" un po' a modo suo
(price_analyzer guardava solo il prezzo, fraud_detector solo i segnali
sospetti). Questo modulo unifica tutto in un singolo punteggio 0-100,
cosi main.py e il bot Telegram condividono esattamente la stessa logica
di classificazione, senza duplicarla.

COME E COMPOSTO LO SCORE (0-100):
- peso_prezzo:        quanto l'annuncio e sotto/sopra il prezzo medio di mercato
- peso_affidabilita:   punteggio di affidabilita calcolato da ai_advisor.py
                        (o dal fallback statistico se l'AI non e configurata)
- peso_fraud:          inverso del punteggio di rischio di fraud_detector.py
                        (rischio basso = contributo positivo allo score)
- peso_foto:           bonus se l'annuncio ha una foto e non emergono
                        anomalie dall'eventuale analisi immagine
- peso_marketplace:    piccolo bonus/malus configurabile per marketplace
                        (es. puoi fidarti di piu di eBay rispetto a uno
                        scraping non ufficiale, se vuoi)

Tutti i pesi sono configurabili in config.PESI_SCORE, cosi puoi
ribilanciare l'importanza relativa senza toccare questo file.
"""

from typing import Optional

import config
from database import Annuncio


def _normalizza_componente_prezzo(annuncio: Annuncio) -> float:
    """
    Ritorna un punteggio 0-100 basato su quanto l'annuncio costa rispetto
    al prezzo medio di mercato. 100 = sconto molto forte, 50 = prezzo in
    linea con la media, 0 = molto sopra la media. Se non c'e ancora un
    prezzo medio calcolato (pochi dati storici), ritorna un valore neutro.
    """
    if not annuncio.prezzo_medio_mercato or annuncio.prezzo_medio_mercato <= 0:
        return 50.0  # nessuna informazione, non penalizzare ne premiare

    sconto = 1 - (annuncio.prezzo / annuncio.prezzo_medio_mercato)
    # sconto 0.5 (50% sotto la media) -> punteggio 100
    # sconto 0   (prezzo in media)    -> punteggio 50
    # sconto -0.5 (50% sopra media)   -> punteggio 0
    punteggio = 50 + (sconto * 100)
    return max(0.0, min(100.0, punteggio))


def _normalizza_componente_affidabilita(annuncio: Annuncio) -> float:
    """Il punteggio di affidabilita e gia 0-100, lo usiamo cosi com'e. Neutro (50) se assente."""
    if annuncio.punteggio_affidabilita is None:
        return 50.0
    return float(annuncio.punteggio_affidabilita)


def _normalizza_componente_fraud(annuncio: Annuncio, punteggio_rischio_fraud: Optional[int]) -> float:
    """
    Il fraud_detector produce un punteggio di RISCHIO (0-100, piu alto =
    piu sospetto). Per lo score finale serve l'inverso: rischio basso deve
    contribuire positivamente. Se non disponibile, valore neutro.
    """
    if punteggio_rischio_fraud is None:
        return 50.0
    return 100.0 - float(punteggio_rischio_fraud)


def _normalizza_componente_foto(annuncio: Annuncio) -> float:
    """
    Bonus se c'e una foto e non sono emerse anomalie dall'eventuale analisi
    immagine. Penalizza leggermente l'assenza di foto (un annuncio senza
    foto e oggettivamente meno valutabile, a prescindere da quanto sia
    "buono" il prezzo).
    """
    if not annuncio.foto_url:
        return 30.0  # nessuna foto: punteggio basso ma non azzerato

    if annuncio.esito_analisi_foto in ("difetti_visibili", "incongruenza_con_descrizione"):
        return 40.0  # foto presente ma con qualche segnale di attenzione
    if annuncio.esito_analisi_foto == "qualita_foto_insufficiente":
        return 60.0
    return 100.0  # foto presente, nessuna anomalia rilevata (o foto non ancora analizzata)


def _normalizza_componente_marketplace(annuncio: Annuncio) -> float:
    """Applica il bonus/malus configurato per marketplace in config.PESI_MARKETPLACE."""
    return float(config.PESI_MARKETPLACE.get(annuncio.piattaforma, 50.0))


def _normalizza_componente_venditore(annuncio: Annuncio) -> float:
    """
    Il punteggio venditore e' gia' 0-100, lo usiamo cosi' com'e'.
    Neutro (50) se non ancora calcolato o se la funzionalita' e' disattivata.
    """
    if annuncio.punteggio_venditore is None:
        return 50.0
    return float(annuncio.punteggio_venditore)


def calcola_score(annuncio: Annuncio, punteggio_rischio_fraud: Optional[int] = None) -> float:
    """
    Calcola lo score finale 0-100 di un annuncio, pesando le componenti
    secondo config.PESI_SCORE. I pesi devono sommare a 1.0 (non e
    obbligatorio matematicamente, ma e l'assunzione con cui sono stati
    tarati i default, per restare nella scala 0-100).

    punteggio_rischio_fraud va passato esplicitamente quando disponibile
    (es. durante l'elaborazione in main.py, dove fraud_detector.valuta()
    e gia stato chiamato) - se omesso, quella componente usa un valore
    neutro, perche fraud_detector non viene rieseguito qui per evitare
    di ricalcolare due volte gli stessi pattern.
    """
    componenti = {
        "prezzo": _normalizza_componente_prezzo(annuncio),
        "affidabilita": _normalizza_componente_affidabilita(annuncio),
        "fraud": _normalizza_componente_fraud(annuncio, punteggio_rischio_fraud),
        "foto": _normalizza_componente_foto(annuncio),
        "marketplace": _normalizza_componente_marketplace(annuncio),
        "venditore": _normalizza_componente_venditore(annuncio),
    }

    score = sum(componenti[chiave] * peso for chiave, peso in config.PESI_SCORE.items())
    return round(max(0.0, min(100.0, score)), 2)


def classifica_annunci(annunci: list[Annuncio]) -> list[Annuncio]:
    """Ordina una lista di annunci per score_finale decrescente (i migliori prima)."""
    return sorted(annunci, key=lambda a: a.score_finale or 0.0, reverse=True)


def e_affare_eccellente(annuncio: Annuncio) -> bool:
    """
    Determina se un annuncio merita la categoria "AFFARI ECCELLENTI" (vedi
    config.SOGLIA_AFFARE_ECCELLENTE) - notifica automatica immediata.
    Richiede contemporaneamente: prezzo molto sotto mercato, fraud score
    basso, affidabilita alta, score complessivo alto. Non basta un singolo
    fattore alto per compensare gli altri: l'intento e segnalare solo le
    occasioni davvero solide su tutti i fronti.
    """
    if annuncio.score_finale is None or annuncio.score_finale < config.SOGLIA_AFFARE_ECCELLENTE:
        return False
    if not annuncio.is_affare:  # gestisce sia bool True/False sia int 1/0 da SQLite
        return False
    if annuncio.punteggio_affidabilita is not None and annuncio.punteggio_affidabilita < config.SOGLIA_AFFIDABILITA_MINIMA_ECCELLENTE:
        return False
    return True
