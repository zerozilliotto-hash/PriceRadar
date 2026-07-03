"""
Logica di paginazione dei risultati di ricerca nel bot Telegram (punto 2
della richiesta).

Lavora sempre sullo StatoSessione di una chat (telegram_state.py): non
esegue mai nuove ricerche sui marketplace, solo slicing/filtri sui
risultati gia presenti in stato.risultati_ids (rispetta il punto 11,
sistema di cache).
"""

import math

import config
import database
import telegram_state
from telegram_state import StatoSessione


def totale_pagine(stato: StatoSessione) -> int:
    """Calcola il numero totale di pagine disponibili, considerando i filtri attivi."""
    import telegram_filters
    ids_filtrati = telegram_filters.applica_filtri(stato.risultati_ids, stato.filtri, stato.ordinamento)
    if not ids_filtrati:
        return 0
    return math.ceil(len(ids_filtrati) / config.RISULTATI_PER_PAGINA)


def vai_a_pagina(stato: StatoSessione, numero_pagina: int) -> tuple:
    """
    Sposta lo stato sulla pagina richiesta (con bound-check: non puo andare
    sotto pagina 1 ne oltre l'ultima pagina disponibile) e ritorna gli
    annunci completi (dict) di quella pagina, insieme al numero di pagina
    effettivo su cui si e finiti.
    """
    n_pagine = totale_pagine(stato)
    if n_pagine == 0:
        return [], 1

    numero_pagina = max(1, min(numero_pagina, n_pagine))
    stato.pagina_corrente = numero_pagina

    ids_pagina = telegram_state.pagina_risultati(stato, numero_pagina, config.RISULTATI_PER_PAGINA)
    telegram_state.segna_come_mostrati(stato, ids_pagina)

    annunci = database.annunci_per_id(ids_pagina)
    return annunci, numero_pagina


def mostra_altri(stato: StatoSessione) -> tuple:
    """
    Implementa il bottone "Mostra altri +5" (punto 1 e 2 della richiesta):
    avanza alla pagina successiva rispetto a quella corrente e ritorna i
    nuovi annunci da mostrare, piu un flag che indica se ce ne sono ancora
    altri dopo questa pagina.
    """
    n_pagine = totale_pagine(stato)

    if stato.pagina_corrente >= n_pagine:
        return [], False  # gia all'ultima pagina, niente altro da mostrare

    annunci, pagina_effettiva = vai_a_pagina(stato, stato.pagina_corrente + 1)
    ha_altri = pagina_effettiva < n_pagine
    return annunci, ha_altri
