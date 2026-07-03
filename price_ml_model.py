"""
Modello di stima del prezzo di mercato che pesa marca, taglia e piattaforma,
oltre allo storico semplice di media/mediana.

PERCHÉ UN MODELLO SEMPLICE (Ridge regression) E NON QUALCOSA PIÙ COMPLESSO:
Con poche decine/centinaia di campioni per profilo di ricerca, un modello
lineare regolarizzato (Ridge) è la scelta giusta: è interpretabile (puoi
vedere quanto pesa ogni fattore), non overfitta con pochi dati come farebbe
un modello più complesso (random forest, reti neurali), ed è velocissimo da
allenare ad ogni ciclo.

COME FUNZIONA:
- Feature categoriche (marca, taglia, piattaforma) → one-hot encoding
- Feature numerica: nessuna oltre al prezzo stesso (target)
- Se non ci sono abbastanza campioni (vedi config.MIN_CAMPIONI_PER_MODELLO_ML),
  il sistema usa automaticamente il fallback statistico (mediana) - vedi
  price_analyzer.py che decide quale strategia usare.

LIMITE ONESTO: con pochi campioni per singola combinazione marca+taglia, la
stima rimane comunque incerta. Il modello aiuta a "smussare" usando tutte le
informazioni disponibili nel profilo, ma non è un oracolo - trattalo come
un'indicazione, non un valore esatto.
"""

from typing import Optional

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder

import config
import database
from database import Annuncio


def _prepara_dataset(profilo_ricerca: str, escludi_id: Optional[str] = None) -> Optional[tuple]:
    """
    Carica lo storico per il profilo e lo trasforma in feature/target per
    il modello. Ritorna None se non ci sono abbastanza campioni.
    """
    with database.get_connection() as conn:
        query = (
            "SELECT marca, taglia, piattaforma, prezzo FROM annunci "
            "WHERE profilo_ricerca = ? AND prezzo > 0"
        )
        params = [profilo_ricerca]
        if escludi_id:
            query += " AND id != ?"
            params.append(escludi_id)
        rows = conn.execute(query, params).fetchall()

    if len(rows) < config.MIN_CAMPIONI_PER_MODELLO_ML:
        return None

    marche = [(r["marca"] or "sconosciuta") for r in rows]
    taglie = [(r["taglia"] or "sconosciuta") for r in rows]
    piattaforme = [r["piattaforma"] for r in rows]
    prezzi = np.array([r["prezzo"] for r in rows], dtype=float)

    X_categorico = np.array(list(zip(marche, taglie, piattaforme)))
    encoder = OneHotEncoder(handle_unknown="ignore")
    X = encoder.fit_transform(X_categorico)

    return X, prezzi, encoder


def stima_prezzo_ml(annuncio: Annuncio) -> Optional[float]:
    """
    Stima il prezzo di mercato atteso per un annuncio usando un modello
    Ridge allenato sullo storico dello stesso profilo di ricerca, pesando
    marca/taglia/piattaforma. Ritorna None se non ci sono abbastanza dati
    storici (in quel caso, usa il fallback a mediana in price_analyzer.py).
    """
    dataset = _prepara_dataset(annuncio.profilo_ricerca, escludi_id=annuncio.id)
    if dataset is None:
        return None

    X, y, encoder = dataset

    modello = Ridge(alpha=1.0)
    try:
        modello.fit(X, y)
    except Exception as e:
        print(f"  [WARN] [ML Prezzi] Errore nell'allenamento del modello: {type(e).__name__} - {e}")
        return None

    riga = np.array([[
        annuncio.marca or "sconosciuta",
        annuncio.taglia or "sconosciuta",
        annuncio.piattaforma,
    ]])
    try:
        X_nuovo = encoder.transform(riga)
        predizione = modello.predict(X_nuovo)[0]
    except Exception as e:
        print(f"  [WARN] [ML Prezzi] Errore nella predizione: {type(e).__name__} - {e}")
        return None

    # Non permettiamo predizioni negative o assurdamente basse
    return round(max(predizione, 1.0), 2)
