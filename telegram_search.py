"""
Ricerca libera avviata da un messaggio di testo scritto dall'utente nel bot
Telegram (es. "maglia adidas", "jordan 4 bianca sotto i 150", "nike tech M").

v2.0: ora integra il query parser NLU (punto 13) e l'espansione multilingua
(punto 5). L'utente puo scrivere in linguaggio naturale e il sistema:
1. Parsifica la query estraendo marca/modello/colore/taglia/prezzo
2. Espande la keyword principale nelle lingue dei marketplace attivi
3. Applica i filtri estratti (prezzo max, taglia) come filtri di sessione

Il contratto principale verso telegram_handlers.py:
esegui_ricerca_libera(query_testo) ritorna (lista_id, query_parsata).
Per i chiamanti v1.0 esiste esegui_ricerca_libera_semplice().
"""

import time
from typing import Optional

import config
import database
import main  # riusa _cerca_su_marketplace e analizza_e_salva, niente duplicazione
import query_parser
import telegram_state


def _unisci_dati_live_con_database(nuovo: database.Annuncio, esistente: dict) -> database.Annuncio:
    """
    Unisce i dati live appena recuperati con quelli gia salvati. Serve per
    correggere annunci vecchi rimasti senza foto/campi v2.0 senza perdere
    traduzioni o analisi gia presenti nel database.
    """
    annuncio = database.annuncio_da_riga(esistente)
    campi_da_riempire = (
        "url", "foto_url", "descrizione", "marca", "taglia", "venditore",
        "condizione", "colore_principale",
    )
    for campo in campi_da_riempire:
        valore_nuovo = getattr(nuovo, campo, None)
        if valore_nuovo and not getattr(annuncio, campo, None):
            setattr(annuncio, campo, valore_nuovo)
    return annuncio


def _richiede_ripristino_v2(nuovo: database.Annuncio, esistente: dict) -> bool:
    """True se l'annuncio salvato manca di dati necessari al bot v2.0."""
    if esistente.get("score_finale") is None:
        return True
    if not esistente.get("foto_url") and nuovo.foto_url:
        return True
    if not esistente.get("condizione") and nuovo.condizione:
        return True
    if not esistente.get("colore_principale") and nuovo.colore_principale:
        return True
    if esistente.get("punteggio_affidabilita") is None:
        return True
    return False


def esegui_ricerca_libera(query_testo: str, prezzo_max: Optional[float] = None) -> tuple[list[str], query_parser.QueryParsata]:
    """
    Esegue una ricerca temporanea su tutti i marketplace attivi.

    v2.0: utilizza query_parser.parse_query_naturale per estrarre attributi
    strutturati dalla query (punto 13), e query_parser.crea_profilo_temporaneo
    per espandere le keyword multilingua (punto 5).

    Ritorna la lista di ID annuncio trovati ordinati per score_finale,
    senza modificare config.SEARCH_PROFILES (ricerca temporanea, punto 5).
    """
    # Parsing NLU della query (punto 13) - se il parsing e' disattivato o
    # l'AI non e' disponibile, torna la query originale come keyword
    query_parsata = query_parser.parse_query_naturale(query_testo)

    # prezzo_max: usa quello estratto dalla query se non passato esplicitamente
    prezzo_effettivo = prezzo_max or query_parsata.prezzo_max

    # Crea profilo temporaneo con keyword espanse multilingua (punto 5)
    profilo_temp = query_parser.crea_profilo_temporaneo_da_query(
        query_parsata,
        f"telegram:{query_testo.strip().lower()}"
    )

    nome_profilo = profilo_temp["nome"]
    keywords = profilo_temp["keywords"]  # lista di keyword multilingua, o [query originale]
    marketplace_da_interrogare = [m for m, attivo in config.MARKETPLACE_ATTIVI.items() if attivo]

    # Se la query parsata indica un marketplace specifico, restringi la ricerca
    if query_parsata.marketplace:
        marketplace_da_interrogare = [
            m for m in marketplace_da_interrogare if m == query_parsata.marketplace
        ]

    risultati_nuovi = []
    for keyword in keywords:
        for nome_marketplace in marketplace_da_interrogare:
            risultati_nuovi.extend(
                main._cerca_su_marketplace(nome_marketplace, keyword, prezzo_effettivo, nome_profilo)
            )
            time.sleep(config.DELAY_TRA_RICERCHE_SECONDI)

    annunci_processati = 0
    ids_visti = set()
    for annuncio in risultati_nuovi:
        if annuncio.id in ids_visti:
            continue
        ids_visti.add(annuncio.id)

        esistente = database.annunci_per_id([annuncio.id])
        if esistente:
            if _richiede_ripristino_v2(annuncio, esistente[0]):
                main.analizza_e_salva(_unisci_dati_live_con_database(annuncio, esistente[0]))
                annunci_processati += 1
            continue

        main.analizza_e_salva(annuncio)
        annunci_processati += 1

    print(
        f"  [SEARCH] Ricerca libera '{query_testo}' "
        f"(keyword espanse: {len(keywords)}, marketplace: {len(marketplace_da_interrogare)}): "
        f"{len(risultati_nuovi)} risultati, {annunci_processati} nuovi analizzati"
    )

    annunci_storici = database.annunci_per_score(profilo_ricerca=nome_profilo)
    return [a["id"] for a in annunci_storici], query_parsata


def esegui_ricerca_libera_semplice(query_testo: str, prezzo_max: Optional[float] = None) -> list[str]:
    """
    Wrapper con firma compatibile con la v1.0 (ritorna solo lista di ID,
    non la query parsata). Usato da telegram_favorites.py e
    telegram_handlers.py dove il chiamante non ha bisogno dei metadati
    della query parsata.
    """
    ids, _ = esegui_ricerca_libera(query_testo, prezzo_max)
    return ids


def aggiorna_ricerca(query_testo: str, prezzo_max: Optional[float] = None) -> list[str]:
    """
    Rifacimento reale della ricerca sui marketplace (l'UNICO posto dove
    avviene scraping su richiesta dell'utente nel bot interattivo).
    Alias di esegui_ricerca_libera_semplice per chiarezza semantica:
    "aggiornare" e' diverso da "cercare per la prima volta", anche se
    tecnicamente fanno la stessa cosa - questa distinzione e' importante
    per la leggibilita' di telegram_handlers.py.
    """
    return esegui_ricerca_libera_semplice(query_testo, prezzo_max)
