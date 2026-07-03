"""
Gestione dello stato di sessione per ogni chat Telegram.

Ogni chat (utente) ha un proprio stato persistente che ricorda:
- l'ultima ricerca effettuata (lista di ID annuncio risultanti, gia
  ordinati per score - cosi "Mostra altri" non deve rifare la ricerca
  ne il ranking, vedi punto 11 "sistema di cache" della richiesta)
- la pagina corrente di paginazione
- i filtri attivi (prezzo, taglia, marketplace, marca)
- l'ordinamento scelto
- quali ID sono gia stati mostrati in questa sessione di ricerca

Lo stato viene serializzato in JSON e salvato nella tabella
telegram_sessions (vedi database.py) cosi sopravvive anche se il bot viene
riavviato - non e tenuto solo in memoria.
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Optional

import database


@dataclass
class FiltriRicerca:
    """Filtri rapidi applicabili dopo una ricerca (punto 9 della richiesta)."""
    prezzo_max: Optional[float] = None
    taglia: Optional[str] = None
    marketplace: Optional[str] = None
    marca: Optional[str] = None
    colore: Optional[str] = None


@dataclass
class StatoSessione:
    """
    Stato completo di una chat. ricerca_id e un identificatore arbitrario
    (qui usiamo un contatore incrementale per sessione) usato nei
    callback_data dei bottoni, per restare sotto il limite di 64 byte di
    Telegram senza dover incollare l'intera query nel bottone (vedi nota in
    telegram_buttons.py).
    """
    ricerca_id: int = 0
    query_originale: str = ""               # testo libero scritto dall'utente, o nome del profilo
    risultati_ids: list = field(default_factory=list)   # tutti gli ID annuncio trovati, gia ordinati per score
    pagina_corrente: int = 1
    ids_mostrati: list = field(default_factory=list)    # ID gia inviati in questa sessione (per "Mostra altri")
    filtri: FiltriRicerca = field(default_factory=FiltriRicerca)
    ordinamento: str = "score"               # "score" | "prezzo" | "recente" | "affidabilita"


def _serializza(stato: StatoSessione) -> str:
    diz = asdict(stato)
    return json.dumps(diz, ensure_ascii=False)


def _deserializza(testo: str) -> StatoSessione:
    diz = json.loads(testo)
    filtri_dict = diz.pop("filtri", {})
    stato = StatoSessione(**diz)
    stato.filtri = FiltriRicerca(**filtri_dict)
    return stato


def carica_stato(chat_id: str) -> StatoSessione:
    """Carica lo stato di una chat, o ne ritorna uno vuoto (nuovo) se non esiste ancora."""
    grezzo = database.carica_sessione(str(chat_id))
    if grezzo is None:
        return StatoSessione()
    try:
        return _deserializza(grezzo)
    except (json.JSONDecodeError, TypeError, KeyError):
        # Stato corrotto o di un formato precedente incompatibile: meglio
        # ripartire da zero che far crashare il bot (vedi punto 18, robustezza)
        return StatoSessione()


def salva_stato(chat_id: str, stato: StatoSessione) -> None:
    """Salva lo stato corrente di una chat, sovrascrivendo quello precedente."""
    database.salva_sessione(str(chat_id), _serializza(stato))


def nuova_ricerca(chat_id: str, query: str, risultati_ids: list) -> StatoSessione:
    """
    Inizializza una nuova sessione di ricerca per una chat, sostituendo
    quella precedente. risultati_ids deve essere gia ordinato per
    pertinenza/score (lo fa telegram_search.py prima di chiamare questa
    funzione).
    """
    stato_precedente = carica_stato(chat_id)
    nuovo_stato = StatoSessione(
        ricerca_id=stato_precedente.ricerca_id + 1,
        query_originale=query,
        risultati_ids=risultati_ids,
        pagina_corrente=1,
        ids_mostrati=[],
    )
    salva_stato(chat_id, nuovo_stato)
    return nuovo_stato


def pagina_risultati(stato: StatoSessione, numero_pagina: int, per_pagina: int) -> list:
    """
    Estrae la slice di ID annuncio corrispondente a una pagina specifica,
    applicando i filtri attivi (la logica di filtro vera e propria e in
    telegram_filters.py - qui viene solo richiamata per evitare di
    duplicare il codice di filtro in piu punti).
    """
    import telegram_filters  # import locale per evitare un ciclo di import con telegram_state

    ids_filtrati = telegram_filters.applica_filtri(stato.risultati_ids, stato.filtri, stato.ordinamento)

    inizio = (numero_pagina - 1) * per_pagina
    fine = inizio + per_pagina
    return ids_filtrati[inizio:fine]


def segna_come_mostrati(stato: StatoSessione, ids: list) -> None:
    """Aggiunge degli ID alla lista di quelli gia mostrati in questa sessione."""
    for id_ in ids:
        if id_ not in stato.ids_mostrati:
            stato.ids_mostrati.append(id_)
