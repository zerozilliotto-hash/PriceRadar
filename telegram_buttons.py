"""
Costruzione delle tastiere inline (pulsanti sotto i messaggi) usate dal bot
Telegram interattivo.

REGOLA IMPORTANTE SU callback_data: Telegram limita callback_data a 64 byte.
Per questo non mettiamo MAI testo libero (query di ricerca, titoli annuncio)
dentro callback_data: usiamo solo identificatori corti (annuncio id, numero
di pagina, nomi di sezione) e recuperiamo i dati veri dallo stato salvato in
telegram_state.py o dal database. Il formato dei callback_data e descritto
sotto, in modo che telegram_handlers.py sappia come fare il parsing inverso.

FORMATO callback_data (sempre "azione:parametro1:parametro2..."):
- "pagina:<numero>"                  -> vai a una pagina specifica dei risultati correnti
- "altri"                            -> mostra altri 5 risultati (avanza pagina)
- "aggiorna"                         -> riesegui la ricerca corrente sui marketplace
- "dashboard"                        -> mostra il link alla dashboard
- "apri:<annuncio_id>"               -> mostra/apri il dettaglio di un annuncio
- "visto:<annuncio_id>"              -> segna un annuncio come visto
- "nascondi_simili:<annuncio_id>"    -> nascondi annunci della stessa marca
- "ignora:<annuncio_id>"             -> ignora solo questo annuncio
- "pref_kw"                          -> aggiungi la query corrente ai preferiti
- "pref_ad:<annuncio_id>"            -> aggiungi un annuncio ai preferiti
- "menu:<nome_sezione>"              -> apri una sezione del menu principale
- "filtro:<campo>:<valore>"          -> applica un filtro rapido
- "ordina:<criterio>"                -> cambia ordinamento
- "storia:<indice>"                  -> rilancia una ricerca dalla cronologia
"""

import hashlib

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config
import database


def _callback_ref(annuncio_id: str) -> str:
    """
    Telegram consente al massimo 64 byte in callback_data. Se l'ID annuncio
    e' troppo lungo, salviamo un riferimento compatto risolvibile dal DB.
    """
    annuncio_id = str(annuncio_id or "")
    if len(annuncio_id.encode("utf-8")) <= 42:
        return annuncio_id
    ref = "ref_" + hashlib.sha1(annuncio_id.encode("utf-8")).hexdigest()[:18]
    database.salva_callback_ref(ref, annuncio_id)
    return ref


def tastiera_menu_principale() -> InlineKeyboardMarkup:
    """Tastiera del menu principale (punto 6 della richiesta)."""
    bottoni = [
        [InlineKeyboardButton("🔍 Cerca prodotto", callback_data="menu:cerca")],
        [InlineKeyboardButton("⭐ Ultimi affari", callback_data="menu:affari")],
        [InlineKeyboardButton("❤️ Preferiti", callback_data="menu:preferiti")],
        [InlineKeyboardButton("📈 Statistiche", callback_data="menu:statistiche")],
        [InlineKeyboardButton("⚙️ Impostazioni", callback_data="menu:impostazioni")],
        [InlineKeyboardButton("🌐 Dashboard", callback_data="dashboard")],
    ]
    return InlineKeyboardMarkup(bottoni)


def tastiera_risultati_ricerca(
    pagina_corrente: int,
    totale_pagine: int,
    ha_altri_da_mostrare: bool,
) -> InlineKeyboardMarkup:
    """
    Tastiera mostrata sotto il riepilogo di una pagina di risultati
    (punto 3: "Mostra altri +5", "Aggiorna ricerca", "Dashboard").
    """
    righe = []

    if totale_pagine > 1:
        riga_nav = []
        if pagina_corrente > 1:
            riga_nav.append(InlineKeyboardButton("◀️", callback_data=f"pagina:{pagina_corrente - 1}"))
        riga_nav.append(InlineKeyboardButton(f"{pagina_corrente}/{totale_pagine}", callback_data="noop"))
        if pagina_corrente < totale_pagine:
            riga_nav.append(InlineKeyboardButton("▶️", callback_data=f"pagina:{pagina_corrente + 1}"))
        righe.append(riga_nav)

    if ha_altri_da_mostrare:
        righe.append([InlineKeyboardButton("➕ Mostra altri +5", callback_data="altri")])

    righe.append([
        InlineKeyboardButton("🔄 Aggiorna ricerca", callback_data="aggiorna"),
        InlineKeyboardButton("🎛 Filtri", callback_data="menu:filtri"),
    ])
    righe.append([
        InlineKeyboardButton("🌐 Dashboard", callback_data="dashboard"),
        InlineKeyboardButton("⭐ Salva ricerca", callback_data="pref_kw"),
    ])

    return InlineKeyboardMarkup(righe)


def tastiera_singolo_annuncio(annuncio_id: str, url: str, ha_originale: bool = False) -> InlineKeyboardMarkup:
    """
    Tastiera sotto la card di un singolo annuncio.
    v2.0: aggiunge bottoni "Traduzione originale" (punto 12) e
    "Ricerca simili" per cercare annunci dello stesso modello.
    """
    ref = _callback_ref(annuncio_id)
    bottoni = []
    if url:
        bottoni.append([InlineKeyboardButton("🔗 Apri annuncio", url=url)])
    bottoni.extend([
        [
            InlineKeyboardButton("👁 Segna come visto", callback_data=f"visto:{ref}"),
            InlineKeyboardButton("❤️ Preferiti", callback_data=f"pref_ad:{ref}"),
        ],
        [
            InlineKeyboardButton("🙈 Nascondi simili", callback_data=f"nascondi_simili:{ref}"),
            InlineKeyboardButton("🚫 Ignora", callback_data=f"ignora:{ref}"),
        ],
        [InlineKeyboardButton("🔍 Ricerca simili", callback_data=f"cerca_simili:{ref}")],
    ])
    if ha_originale:
        bottoni.append([InlineKeyboardButton("🌐 Testo originale", callback_data=f"originale:{ref}")])
    return InlineKeyboardMarkup(bottoni)


def tastiera_filtri_rapidi() -> InlineKeyboardMarkup:
    """
    Tastiera per i filtri rapidi dopo una ricerca (punto 9: prezzo, taglia,
    marketplace, marca, ordinamento).
    """
    bottoni = [
        [InlineKeyboardButton("💰 Filtra per prezzo", callback_data="menu:filtro_prezzo")],
        [InlineKeyboardButton("📏 Filtra per taglia", callback_data="menu:filtro_taglia")],
        [InlineKeyboardButton("🏪 Filtra per marketplace", callback_data="menu:filtro_marketplace")],
        [InlineKeyboardButton("🏷 Filtra per marca", callback_data="menu:filtro_marca")],
        [
            InlineKeyboardButton("📊 Ordina: Affare", callback_data="ordina:score"),
            InlineKeyboardButton("💶 Ordina: Prezzo", callback_data="ordina:prezzo"),
        ],
        [
            InlineKeyboardButton("🕒 Ordina: Recenti", callback_data="ordina:recente"),
            InlineKeyboardButton("✅ Ordina: Affidabilità", callback_data="ordina:affidabilita"),
        ],
        [InlineKeyboardButton("♻️ Rimuovi tutti i filtri", callback_data="filtro:reset:tutti")],
        [InlineKeyboardButton("⬅️ Torna ai risultati", callback_data="pagina:1")],
    ]
    return InlineKeyboardMarkup(bottoni)


def tastiera_marketplace_disponibili() -> InlineKeyboardMarkup:
    """Tastiera per scegliere un marketplace specifico come filtro."""
    nomi = {"vinted": "Vinted", "ebay": "eBay", "depop": "Depop", "subito": "Subito.it"}
    bottoni = [
        [InlineKeyboardButton(nomi.get(m, m), callback_data=f"filtro:marketplace:{m}")]
        for m, attivo in config.MARKETPLACE_ATTIVI.items() if attivo
    ]
    bottoni.append([InlineKeyboardButton("⬅️ Indietro", callback_data="menu:filtri")])
    return InlineKeyboardMarkup(bottoni)


def tastiera_preferiti(preferiti: list) -> InlineKeyboardMarkup:
    """
    Tastiera per la sezione preferiti: un bottone per controllare tutti i
    preferiti insieme, piu un bottone di rimozione per ciascuno.
    """
    righe = [[InlineKeyboardButton("🔄 Controlla tutti i preferiti", callback_data="controlla_preferiti")]]
    for p in preferiti[:10]:
        etichetta = p["keyword"] if p["tipo"] == "keyword" else f"Annuncio {p['annuncio_id']}"
        righe.append([
            InlineKeyboardButton(f"❌ {etichetta[:30]}", callback_data=f"rimuovi_pref:{p['id']}"),
        ])
    righe.append([InlineKeyboardButton("⬅️ Menu principale", callback_data="menu:home")])
    return InlineKeyboardMarkup(righe)


def tastiera_cronologia(cronologia: list) -> InlineKeyboardMarkup:
    """Tastiera per la sezione cronologia: un bottone per rilanciare ogni ricerca passata."""
    righe = []
    for i, voce in enumerate(cronologia[:10]):
        etichetta = f"{voce['query'][:30]} ({voce['risultati_trovati']} risultati)"
        righe.append([InlineKeyboardButton(etichetta, callback_data=f"storia:{i}")])
    righe.append([InlineKeyboardButton("⬅️ Menu principale", callback_data="menu:home")])
    return InlineKeyboardMarkup(righe)


def tastiera_indietro_a_menu() -> InlineKeyboardMarkup:
    """Tastiera minima con solo il ritorno al menu principale, per schermate semplici."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu principale", callback_data="menu:home")]])
