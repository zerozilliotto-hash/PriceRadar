"""
Analisi prezzi: calcola se un annuncio è un "affare" rispetto allo storico
di prezzi raccolto per lo stesso profilo di ricerca.

Due strategie disponibili (vedi config.MODELLO_PREZZO):
- "mediana": statistica pura, trasparente, funziona da subito con pochi dati
- "ml": modello di regressione che pesa anche marca/taglia/piattaforma,
  più accurato ma richiede più campioni storici (vedi price_ml_model.py)

Se scegli "ml" ma non ci sono ancora abbastanza campioni per quel profilo,
il sistema ricade automaticamente sulla mediana, senza errori.
"""

from typing import Optional

import config
import database
import price_ml_model
from database import Annuncio


def analizza_prezzo(annuncio: Annuncio) -> Annuncio:
    """
    Calcola il prezzo medio di mercato storico per il profilo di ricerca
    dell'annuncio, e determina se è un affare. Modifica l'annuncio sul posto
    e lo ritorna.
    """
    prezzo_riferimento = None

    if config.MODELLO_PREZZO == "ml":
        prezzo_riferimento = price_ml_model.stima_prezzo_ml(annuncio)

    if prezzo_riferimento is None:
        # fallback (o scelta esplicita) sulla mediana storica
        stats = database.prezzo_medio_per_profilo(annuncio.profilo_ricerca, escludi_id=annuncio.id)
        if stats is None:
            annuncio.prezzo_medio_mercato = None
            annuncio.is_affare = None
            return annuncio
        prezzo_riferimento = stats["mediana"]

    annuncio.prezzo_medio_mercato = round(prezzo_riferimento, 2)

    if annuncio.prezzo <= 0:
        annuncio.is_affare = False
        return annuncio

    sconto = 1 - (annuncio.prezzo / annuncio.prezzo_medio_mercato)
    annuncio.is_affare = sconto >= config.SOGLIA_AFFARE
    return annuncio


def descrizione_sconto(annuncio: Annuncio) -> str:
    """Ritorna una stringa leggibile sulla posizione di prezzo dell'annuncio."""
    if annuncio.prezzo_medio_mercato is None:
        return "Prezzo medio non ancora disponibile (servono più dati storici)"

    diff = annuncio.prezzo_medio_mercato - annuncio.prezzo
    perc = (diff / annuncio.prezzo_medio_mercato) * 100 if annuncio.prezzo_medio_mercato else 0

    if diff > 0:
        return f"{perc:.0f}% sotto il prezzo medio ({annuncio.prezzo_medio_mercato}€ → {annuncio.prezzo}€)"
    elif diff < 0:
        return f"{abs(perc):.0f}% sopra il prezzo medio ({annuncio.prezzo_medio_mercato}€ → {annuncio.prezzo}€)"
    else:
        return f"In linea col prezzo medio ({annuncio.prezzo_medio_mercato}€)"
