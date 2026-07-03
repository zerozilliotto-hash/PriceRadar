"""
Handler principali del bot Telegram interattivo.

Questo modulo collega tutti gli altri moduli telegram_* alle funzioni di
callback richieste da python-telegram-bot (PTB):
- comandi (/start, /help, /search, ecc. - punto 13 della richiesta)
- messaggi di testo libero (punto 4: l'utente scrive una query senza comandi)
- callback dei bottoni inline (punto 3: ogni interazione con i pulsanti)

ROBUSTEZZA (punto 18): ogni handler e avvolto in try/except per non far
crashare il bot su errori imprevisti (timeout, API non disponibili,
risultati vuoti, sessioni scadute, callback_data malformato). In caso di
errore, l'utente riceve un messaggio comprensibile invece di nessuna
risposta o di un crash silenzioso del processo.
"""

import logging
from html import escape

from telegram import Update
from telegram.ext import ContextTypes

import config
import database
import telegram_state
import telegram_buttons
import telegram_menu
import telegram_search
import telegram_pagination
import telegram_filters
import telegram_favorites

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# UTILITY INTERNE
# ----------------------------------------------------------------------------

def _h(valore) -> str:
    return escape(str(valore), quote=False) if valore is not None else ""


def _annuncio_id_da_callback(dati: list) -> str:
    if len(dati) < 2:
        return ""
    return database.risolvi_callback_ref(dati[1])


def _tastiera_card_annuncio(annuncio: dict):
    return telegram_buttons.tastiera_singolo_annuncio(
        annuncio["id"],
        annuncio.get("url") or "",
        ha_originale=telegram_menu.annuncio_ha_testo_originale(annuncio),
    )


async def _invia_card_annuncio(target, annuncio: dict) -> None:
    """
    Invia una card completa: foto quando disponibile, dettagli v2.0 e
    bottoni azione. Se la caption supera il limite Telegram, manda la foto
    con una caption breve e poi il testo completo con i pulsanti.
    """
    testo_card = telegram_menu.testo_card_annuncio(annuncio)
    tastiera_card = _tastiera_card_annuncio(annuncio)

    if annuncio.get("foto_url"):
        try:
            if len(testo_card) <= 1024:
                await target.reply_photo(
                    photo=annuncio["foto_url"],
                    caption=testo_card,
                    reply_markup=tastiera_card,
                    parse_mode="HTML",
                )
                return

            caption_breve = "\n".join(testo_card.splitlines()[:3])
            await target.reply_photo(
                photo=annuncio["foto_url"],
                caption=caption_breve[:1000],
                parse_mode="HTML",
            )
            await target.reply_text(testo_card, reply_markup=tastiera_card, parse_mode="HTML")
            return
        except Exception as e:
            logger.warning(f"Invio foto fallito per {annuncio['id']}, fallback a testo: {e}")

    await target.reply_text(testo_card, reply_markup=tastiera_card, parse_mode="HTML")


async def _invia_pagina_risultati(update_o_query, chat_id: str, stato, nuovi_annunci=False) -> None:
    """
    Invia (o modifica, se chiamata da un callback) il messaggio con il
    riepilogo della pagina corrente e le relative card annuncio. Centralizza
    qui questa logica perche viene usata da piu handler (ricerca nuova,
    cambio pagina, mostra altri, cambio filtro).
    """
    n_pagine = telegram_pagination.totale_pagine(stato)
    target = update_o_query.message if hasattr(update_o_query, "message") else update_o_query

    if n_pagine == 0:
        testo = telegram_menu.testo_nessun_risultato(stato.query_originale)
        await target.reply_text(testo, parse_mode="HTML")
        return

    annunci, pagina_effettiva = telegram_pagination.vai_a_pagina(stato, stato.pagina_corrente)
    telegram_state.salva_stato(chat_id, stato)

    ids_filtrati_totali = telegram_filters.applica_filtri(stato.risultati_ids, stato.filtri, stato.ordinamento)
    filtri_desc = telegram_filters.descrizione_filtri_attivi(stato.filtri)

    intestazione = telegram_menu.testo_riepilogo_pagina(
        stato.query_originale, pagina_effettiva, n_pagine, len(ids_filtrati_totali), filtri_desc
    )

    ha_altri = (pagina_effettiva < n_pagine) or any(
        a_id not in stato.ids_mostrati for a_id in ids_filtrati_totali
    )

    tastiera = telegram_buttons.tastiera_risultati_ricerca(pagina_effettiva, n_pagine, ha_altri)

    await target.reply_text(intestazione, reply_markup=tastiera, parse_mode="HTML")

    for annuncio in annunci:
        await _invia_card_annuncio(target, annuncio)


# ----------------------------------------------------------------------------
# COMANDI (punto 13 della richiesta)
# ----------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce /start: messaggio di benvenuto + menu principale."""
    try:
        nome = update.effective_user.first_name or "utente"
        await update.message.reply_text(
            telegram_menu.testo_benvenuto(nome),
            reply_markup=telegram_buttons.tastiera_menu_principale(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Errore in cmd_start: {e}")
        await _messaggio_errore_generico(update)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.reply_text(telegram_menu.testo_help(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Errore in cmd_help: {e}")
        await _messaggio_errore_generico(update)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/search senza argomenti chiede cosa cercare; con argomenti avvia subito la ricerca."""
    try:
        argomenti = " ".join(context.args) if context.args else ""
        if not argomenti:
            await update.message.reply_text("🔍 Scrivimi cosa vuoi cercare (es. <i>nike tech fleece</i>)", parse_mode="HTML")
            return
        await _avvia_ricerca_libera(update, update.effective_chat.id, argomenti)
    except Exception as e:
        logger.error(f"Errore in cmd_search: {e}")
        await _messaggio_errore_generico(update)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        chat_id = str(update.effective_chat.id)
        cronologia = database.lista_cronologia(chat_id)
        if not cronologia:
            await update.message.reply_text(telegram_menu.testo_cronologia_vuota())
            return
        righe = ["📜 <b>Le tue ultime ricerche</b>\n"]
        for voce in cronologia:
            righe.append(f"• {_h(voce['query'])} ({voce['risultati_trovati']} risultati)")
        await update.message.reply_text(
            "\n".join(righe), reply_markup=telegram_buttons.tastiera_cronologia(cronologia), parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Errore in cmd_history: {e}")
        await _messaggio_errore_generico(update)


async def cmd_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        chat_id = str(update.effective_chat.id)
        preferiti = telegram_favorites.elenco_preferiti(chat_id)
        if not preferiti:
            await update.message.reply_text(telegram_menu.testo_preferiti_vuoti())
            return
        await update.message.reply_text(
            "❤️ <b>I tuoi preferiti</b>", reply_markup=telegram_buttons.tastiera_preferiti(preferiti), parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Errore in cmd_favorites: {e}")
        await _messaggio_errore_generico(update)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.reply_text(telegram_menu.testo_statistiche(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Errore in cmd_stats: {e}")
        await _messaggio_errore_generico(update)


async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.reply_text(telegram_menu.testo_dashboard())
    except Exception as e:
        logger.error(f"Errore in cmd_dashboard: {e}")
        await _messaggio_errore_generico(update)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        marketplace_attivi = ", ".join(m for m, attivo in config.MARKETPLACE_ATTIVI.items() if attivo)
        testo = (
            "⚙️ <b>Impostazioni</b>\n\n"
            f"Marketplace attivi: {marketplace_attivi}\n"
            f"Risultati per pagina: {config.RISULTATI_PER_PAGINA}\n"
            f"Soglia affare eccellente: score ≥ {config.SOGLIA_AFFARE_ECCELLENTE}\n\n"
            "Per modificare queste impostazioni, contatta l'amministratore del bot "
            "(si modificano da config.py)."
        )
        await update.message.reply_text(testo, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Errore in cmd_settings: {e}")
        await _messaggio_errore_generico(update)


# ----------------------------------------------------------------------------
# MESSAGGI DI TESTO LIBERO (punto 4 della richiesta)
# ----------------------------------------------------------------------------

async def gestisci_testo_libero(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Qualsiasi messaggio di testo che non sia un comando viene interpretato
    automaticamente come query di ricerca (punto 4: niente /search
    obbligatorio).
    """
    try:
        testo = (update.message.text or "").strip()
        if not testo:
            return
        await _avvia_ricerca_libera(update, update.effective_chat.id, testo)
    except Exception as e:
        logger.error(f"Errore in gestisci_testo_libero: {e}")
        await _messaggio_errore_generico(update)


async def _avvia_ricerca_libera(update: Update, chat_id, query_testo: str) -> None:
    """
    Esegue la ricerca libera vera e propria (punto 4 e 5): cerca sui
    marketplace, salva la cronologia, inizializza lo stato di sessione e
    invia la prima pagina di risultati.

    v2.0: usa la nuova firma di telegram_search che ritorna anche la
    query parsata, cosi i filtri estratti (es. taglia, colore) vengono
    pre-impostati nella sessione prima di mostrare i risultati.
    """
    chat_id = str(chat_id)
    await update.message.reply_text(f"🔎 Cerco <b>{_h(query_testo)}</b> su tutti i marketplace attivi...", parse_mode="HTML")

    try:
        risultati_ids, query_parsata = telegram_search.esegui_ricerca_libera(query_testo)
    except Exception as e:
        logger.error(f"Errore durante la ricerca libera per '{query_testo}': {e}")
        await update.message.reply_text(
            "⚠️ Si e verificato un problema durante la ricerca (un marketplace potrebbe "
            "essere temporaneamente non raggiungibile). Riprova tra poco."
        )
        return

    risultati_ids = [
        a["id"] for a in database.filtra_ignorati(chat_id, database.annunci_per_id(risultati_ids))
    ]

    database.salva_ricerca_cronologia(chat_id, query_testo, len(risultati_ids))

    if not risultati_ids:
        await update.message.reply_text(telegram_menu.testo_nessun_risultato(query_testo), parse_mode="HTML")
        return

    stato = telegram_state.nuova_ricerca(chat_id, query_testo, risultati_ids)

    # Pre-imposta filtri estratti dalla query NLU (taglia, marketplace)
    if query_parsata.taglia:
        stato.filtri.taglia = query_parsata.taglia
    if query_parsata.marketplace:
        stato.filtri.marketplace = query_parsata.marketplace
    if query_parsata.colore:
        stato.filtri.colore = query_parsata.colore
    telegram_state.salva_stato(chat_id, stato)

    await _invia_pagina_risultati(update, chat_id, stato)


# ----------------------------------------------------------------------------
# CALLBACK DEI BOTTONI (punto 3 della richiesta)
# ----------------------------------------------------------------------------

async def gestisci_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Router centrale per tutti i click sui bottoni inline. Fa il parsing del
    callback_data secondo il formato documentato in telegram_buttons.py e
    smista alla funzione giusta. Avvolto in try/except generale per
    robustezza (punto 18: callback scadute, sessioni scadute non devono
    crashare il bot).
    """
    query = update.callback_query
    try:
        await query.answer()  # ferma l'animazione di caricamento sul bottone, sempre necessario
    except Exception:
        pass  # se la callback e scaduta, query.answer() puo fallire - non e bloccante

    try:
        chat_id = str(update.effective_chat.id)
        dati = (query.data or "").split(":")
        azione = dati[0] if dati else ""

        if azione == "noop":
            return  # bottone puramente decorativo (es. indicatore pagina), nessuna azione

        if azione == "menu":
            await _gestisci_menu(query, chat_id, dati[1] if len(dati) > 1 else "home")
        elif azione == "pagina":
            await _gestisci_cambio_pagina(query, chat_id, dati)
        elif azione == "altri":
            await _gestisci_mostra_altri(query, chat_id)
        elif azione == "aggiorna":
            await _gestisci_aggiorna_ricerca(query, chat_id)
        elif azione == "dashboard":
            await query.message.reply_text(telegram_menu.testo_dashboard())
        elif azione == "storia":
            await _gestisci_rilancia_da_storia(query, chat_id, dati)
        elif azione == "visto":
            await _gestisci_segna_visto(query, chat_id, dati)
        elif azione == "nascondi_simili":
            await _gestisci_nascondi_simili(query, chat_id, dati)
        elif azione == "ignora":
            await _gestisci_ignora(query, chat_id, dati)
        elif azione == "pref_kw":
            await _gestisci_salva_keyword_preferita(query, chat_id)
        elif azione == "pref_ad":
            await _gestisci_salva_annuncio_preferito(query, chat_id, dati)
        elif azione == "rimuovi_pref":
            await _gestisci_rimuovi_preferito(query, chat_id, dati)
        elif azione == "controlla_preferiti":
            await _gestisci_controlla_preferiti(query, chat_id)
        elif azione == "cerca_simili":
            await _gestisci_cerca_simili(query, chat_id, dati)
        elif azione == "originale":
            await _gestisci_mostra_originale(query, chat_id, dati)
        elif azione == "filtro":
            await _gestisci_filtro(query, chat_id, dati)
        elif azione == "ordina":
            await _gestisci_ordinamento(query, chat_id, dati)
        else:
            logger.warning(f"Callback non riconosciuto: {query.data}")

    except Exception as e:
        logger.error(f"Errore nella gestione del callback '{query.data}': {e}")
        try:
            await query.message.reply_text(
                "⚠️ Qualcosa e andato storto con questa azione. Prova a rifare la ricerca con /search."
            )
        except Exception:
            pass  # se anche l'invio del messaggio di errore fallisce, non c'e altro da fare qui


async def _gestisci_menu(query, chat_id: str, sezione: str) -> None:
    """Gestisce la navigazione tra le sezioni del menu principale (punto 6)."""
    if sezione == "home":
        await query.message.reply_text(
            telegram_menu.testo_benvenuto(query.from_user.first_name or "utente"),
            reply_markup=telegram_buttons.tastiera_menu_principale(), parse_mode="HTML",
        )
    elif sezione == "cerca":
        await query.message.reply_text("🔍 Scrivimi cosa vuoi cercare (es. <i>nike tech fleece</i>)", parse_mode="HTML")
    elif sezione == "affari":
        await query.message.reply_text(telegram_menu.testo_sezione_affari(), parse_mode="HTML")
    elif sezione == "preferiti":
        preferiti = telegram_favorites.elenco_preferiti(chat_id)
        if not preferiti:
            await query.message.reply_text(telegram_menu.testo_preferiti_vuoti())
        else:
            await query.message.reply_text(
                "❤️ <b>I tuoi preferiti</b>", reply_markup=telegram_buttons.tastiera_preferiti(preferiti), parse_mode="HTML",
            )
    elif sezione == "statistiche":
        await query.message.reply_text(telegram_menu.testo_statistiche(), parse_mode="HTML")
    elif sezione == "impostazioni":
        marketplace_attivi = ", ".join(m for m, attivo in config.MARKETPLACE_ATTIVI.items() if attivo)
        await query.message.reply_text(f"⚙️ Marketplace attivi: {marketplace_attivi}")
    elif sezione == "filtri":
        await query.message.reply_text("🎛 <b>Filtri rapidi</b>", reply_markup=telegram_buttons.tastiera_filtri_rapidi(), parse_mode="HTML")
    elif sezione == "filtro_marketplace":
        await query.message.reply_text("🏪 Scegli un marketplace:", reply_markup=telegram_buttons.tastiera_marketplace_disponibili())
    elif sezione in ("filtro_prezzo", "filtro_taglia", "filtro_marca"):
        nomi = {"filtro_prezzo": "il prezzo massimo (es. 50)", "filtro_taglia": "la taglia (es. M)", "filtro_marca": "la marca (es. Nike)"}
        await query.message.reply_text(
            f"✏️ Scrivimi {nomi[sezione]} nel prossimo messaggio.\n"
            f"(Questa funzione testuale e una versione semplificata: per ora puoi anche "
            f"usare i filtri marketplace dai bottoni, gli altri filtri via testo libero "
            f"verranno raffinati in una prossima iterazione)"
        )


async def _gestisci_cambio_pagina(query, chat_id: str, dati: list) -> None:
    stato = telegram_state.carica_stato(chat_id)
    if not stato.risultati_ids:
        await query.message.reply_text("⚠️ Questa ricerca non e piu disponibile. Avviane una nuova scrivendo cosa cerchi.")
        return
    try:
        numero_pagina = int(dati[1]) if len(dati) > 1 else 1
    except ValueError:
        numero_pagina = 1
    stato.pagina_corrente = numero_pagina
    await _invia_pagina_risultati(query, chat_id, stato)


async def _gestisci_mostra_altri(query, chat_id: str) -> None:
    """Punto 1, 2, 11: mostra altri 5 risultati, senza rifare scraping."""
    stato = telegram_state.carica_stato(chat_id)
    if not stato.risultati_ids:
        await query.message.reply_text("⚠️ Questa ricerca non e piu disponibile. Avviane una nuova scrivendo cosa cerchi.")
        return

    annunci, ha_altri = telegram_pagination.mostra_altri(stato)
    telegram_state.salva_stato(chat_id, stato)

    if not annunci:
        await query.message.reply_text("✅ Hai visto tutti i risultati disponibili per questa ricerca.")
        return

    for annuncio in annunci:
        await _invia_card_annuncio(query.message, annuncio)

    if ha_altri:
        n_pagine = telegram_pagination.totale_pagine(stato)
        await query.message.reply_text(
            "Altri disponibili:",
            reply_markup=telegram_buttons.tastiera_risultati_ricerca(stato.pagina_corrente, n_pagine, True),
        )


async def _gestisci_aggiorna_ricerca(query, chat_id: str) -> None:
    """Punto 3 e 11: questo e l'UNICO bottone che rifa scraping reale."""
    stato = telegram_state.carica_stato(chat_id)
    if not stato.query_originale:
        await query.message.reply_text("⚠️ Nessuna ricerca da aggiornare. Scrivimi cosa cerchi.")
        return

    await query.message.reply_text(f"🔄 Aggiorno la ricerca per <b>{_h(stato.query_originale)}</b>...", parse_mode="HTML")
    try:
        risultati_ids = telegram_search.aggiorna_ricerca(stato.query_originale)
    except Exception as e:
        logger.error(f"Errore nell'aggiornamento ricerca: {e}")
        await query.message.reply_text("⚠️ Aggiornamento non riuscito, riprova tra poco.")
        return

    risultati_ids = [a["id"] for a in database.filtra_ignorati(chat_id, database.annunci_per_id(risultati_ids))]
    nuovo_stato = telegram_state.nuova_ricerca(chat_id, stato.query_originale, risultati_ids)
    await _invia_pagina_risultati(query, chat_id, nuovo_stato)


async def _gestisci_segna_visto(query, chat_id: str, dati: list) -> None:
    annuncio_id = _annuncio_id_da_callback(dati)
    if not annuncio_id:
        return
    database.segna_visto(chat_id, annuncio_id)
    await query.message.reply_text("👁 Segnato come visto.")


async def _gestisci_nascondi_simili(query, chat_id: str, dati: list) -> None:
    annuncio_id = _annuncio_id_da_callback(dati)
    if not annuncio_id:
        return
    annuncio = database.annunci_per_id([annuncio_id])
    if not annuncio or not annuncio[0].get("marca"):
        await query.message.reply_text("⚠️ Non posso nascondere annunci simili: marca non disponibile per questo annuncio.")
        return
    database.ignora_pattern(chat_id, "marca", annuncio[0]["marca"])
    await query.message.reply_text(f"🙈 Nasconderò gli annunci di marca \"{annuncio[0]['marca']}\" nelle prossime ricerche.")


async def _gestisci_ignora(query, chat_id: str, dati: list) -> None:
    annuncio_id = _annuncio_id_da_callback(dati)
    if not annuncio_id:
        return
    database.ignora_pattern(chat_id, "annuncio_singolo", annuncio_id)
    await query.message.reply_text("🚫 Annuncio ignorato.")


async def _gestisci_salva_keyword_preferita(query, chat_id: str) -> None:
    stato = telegram_state.carica_stato(chat_id)
    if not stato.query_originale:
        await query.message.reply_text("⚠️ Nessuna ricerca attiva da salvare.")
        return
    telegram_favorites.aggiungi_keyword_ai_preferiti(chat_id, stato.query_originale)
    await query.message.reply_text(f"⭐ \"{stato.query_originale}\" salvata nei preferiti.")


async def _gestisci_salva_annuncio_preferito(query, chat_id: str, dati: list) -> None:
    annuncio_id = _annuncio_id_da_callback(dati)
    if not annuncio_id:
        return
    telegram_favorites.aggiungi_annuncio_ai_preferiti(chat_id, annuncio_id)
    await query.message.reply_text("❤️ Annuncio salvato nei preferiti.")


async def _gestisci_rimuovi_preferito(query, chat_id: str, dati: list) -> None:
    if len(dati) < 2:
        return
    try:
        preferito_id = int(dati[1])
    except ValueError:
        return
    telegram_favorites.rimuovi_dai_preferiti(chat_id, preferito_id)
    await query.message.reply_text("✅ Rimosso dai preferiti.")


async def _gestisci_controlla_preferiti(query, chat_id: str) -> None:
    await query.message.reply_text("🔄 Controllo i tuoi preferiti...")
    try:
        risultato = telegram_favorites.controlla_tutti_i_preferiti(chat_id)
    except Exception as e:
        logger.error(f"Errore nel controllo preferiti: {e}")
        await query.message.reply_text("⚠️ Controllo non riuscito, riprova tra poco.")
        return

    if not risultato["per_keyword"] and not risultato["annunci_preferiti_aggiornati"]:
        await query.message.reply_text(telegram_menu.testo_preferiti_vuoti())
        return

    for kw, ids in risultato["per_keyword"].items():
        await query.message.reply_text(f"📌 <b>{_h(kw)}</b>: {len(ids)} risultati trovati", parse_mode="HTML")

    for annuncio in risultato["annunci_preferiti_aggiornati"]:
        await _invia_card_annuncio(query.message, annuncio)


async def _gestisci_rilancia_da_storia(query, chat_id: str, dati: list) -> None:
    if len(dati) < 2:
        return
    try:
        indice = int(dati[1])
    except ValueError:
        return
    cronologia = database.lista_cronologia(chat_id)
    if indice >= len(cronologia):
        await query.message.reply_text("⚠️ Questa voce di cronologia non e piu disponibile.")
        return
    query_testo = cronologia[indice]["query"]
    await query.message.reply_text(f"🔁 Rilancio la ricerca: <b>{_h(query_testo)}</b>", parse_mode="HTML")
    risultati_ids = telegram_search.esegui_ricerca_libera_semplice(query_testo)
    risultati_ids = [a["id"] for a in database.filtra_ignorati(chat_id, database.annunci_per_id(risultati_ids))]
    if not risultati_ids:
        await query.message.reply_text(telegram_menu.testo_nessun_risultato(query_testo), parse_mode="HTML")
        return
    stato = telegram_state.nuova_ricerca(chat_id, query_testo, risultati_ids)
    await _invia_pagina_risultati(query, chat_id, stato)


async def _gestisci_cerca_simili(query, chat_id: str, dati: list) -> None:
    """
    Cerca annunci simili a quello selezionato, usando il modello/marca
    riconosciuti come keyword di ricerca (punto 1 v2.0: la ricerca usa
    il modello strutturato, non solo il titolo testuale).
    """
    annuncio_id = _annuncio_id_da_callback(dati)
    if not annuncio_id:
        return
    annunci = database.annunci_per_id([annuncio_id])
    if not annunci:
        await query.message.reply_text("⚠️ Annuncio non trovato nel database.")
        return

    a = annunci[0]
    # Costruisce una keyword di ricerca strutturata: usa modello se disponibile,
    # altrimenti marca + prima parte del titolo
    if a.get("modello"):
        keyword = a["modello"]
        if a.get("edizione"):
            keyword = f"{keyword} {a['edizione']}"
    elif a.get("marca"):
        keyword = a["marca"]
    else:
        keyword = (a.get("titolo") or "")[:40]

    await query.message.reply_text(f"🔍 Cerco annunci simili: <b>{_h(keyword)}</b>", parse_mode="HTML")
    risultati_ids = telegram_search.esegui_ricerca_libera_semplice(keyword)
    risultati_ids = [r for r in risultati_ids if r != annuncio_id]  # escludi l'annuncio di partenza
    risultati_ids = [
        a["id"]
        for a in database.filtra_ignorati(chat_id, database.annunci_per_id(risultati_ids))
    ]

    if not risultati_ids:
        await query.message.reply_text(telegram_menu.testo_nessun_risultato(keyword), parse_mode="HTML")
        return

    stato = telegram_state.nuova_ricerca(chat_id, keyword, risultati_ids)
    await _invia_pagina_risultati(query, chat_id, stato)


async def _gestisci_mostra_originale(query, chat_id: str, dati: list) -> None:
    """
    Mostra il testo originale (pre-traduzione) di un annuncio, se disponibile
    (punto 4, 12 della v2.0: bottone 'Traduzione originale').
    """
    annuncio_id = _annuncio_id_da_callback(dati)
    if not annuncio_id:
        return
    annunci = database.annunci_per_id([annuncio_id])
    if not annunci:
        await query.message.reply_text("⚠️ Annuncio non trovato.")
        return

    a = annunci[0]
    titolo_orig = a.get("titolo_originale") or a.get("titolo", "N/D")
    desc_orig = a.get("descrizione_originale") or a.get("descrizione") or ""
    lingua = a.get("lingua_originale", "?").upper()

    testo = f"🌐 <b>Testo originale [{_h(lingua)}]</b>\n\n<b>{_h(titolo_orig)}</b>"
    if desc_orig:
        testo += f"\n\n{_h(desc_orig[:1200])}"
    await query.message.reply_text(testo, parse_mode="HTML")


async def _gestisci_filtro(query, chat_id: str, dati: list) -> None:
    """Applica un filtro rapido (punto 9) e ri-mostra la pagina corrente filtrata."""
    if len(dati) < 3:
        return
    campo, valore = dati[1], dati[2]

    stato = telegram_state.carica_stato(chat_id)
    if not stato.risultati_ids:
        await query.message.reply_text("⚠️ Nessuna ricerca attiva su cui applicare filtri.")
        return

    if campo == "reset":
        stato.filtri = telegram_state.FiltriRicerca()
    elif campo == "marketplace":
        stato.filtri.marketplace = valore
    elif campo == "marca":
        stato.filtri.marca = valore
    elif campo == "taglia":
        stato.filtri.taglia = valore
    elif campo == "prezzo_max":
        try:
            stato.filtri.prezzo_max = float(valore)
        except ValueError:
            pass
    elif campo == "colore":
        stato.filtri.colore = valore

    stato.pagina_corrente = 1
    await _invia_pagina_risultati(query, chat_id, stato)


async def _gestisci_ordinamento(query, chat_id: str, dati: list) -> None:
    """Cambia il criterio di ordinamento (punto 9) e ri-mostra la pagina corrente."""
    if len(dati) < 2:
        return
    criterio = dati[1]
    if criterio not in ("score", "prezzo", "recente", "affidabilita"):
        return

    stato = telegram_state.carica_stato(chat_id)
    if not stato.risultati_ids:
        await query.message.reply_text("⚠️ Nessuna ricerca attiva su cui cambiare ordinamento.")
        return

    stato.ordinamento = criterio
    stato.pagina_corrente = 1
    await _invia_pagina_risultati(query, chat_id, stato)


# ----------------------------------------------------------------------------
# GESTIONE ERRORI GLOBALE (punto 18 della richiesta)
# ----------------------------------------------------------------------------

async def _messaggio_errore_generico(update: Update) -> None:
    """Messaggio di fallback mostrato quando un handler fallisce in modo imprevisto."""
    try:
        if update.message:
            await update.message.reply_text(
                "⚠️ Si e verificato un errore imprevisto. Riprova, o scrivi /start per tornare al menu principale."
            )
    except Exception:
        pass  # se anche questo fallisce, non c'e piu nulla da fare lato bot


async def gestisci_errori_globali(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Error handler registrato a livello di Application (vedi
    telegram_interactive_bot.py): cattura qualsiasi eccezione non gestita
    nei singoli handler, la logga, e prova ad avvisare l'utente senza far
    crashare il processo del bot.
    """
    logger.error(f"Eccezione non gestita: {context.error}", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ Si e verificato un errore tecnico. Il bot continua a funzionare: riprova tra poco."
            )
    except Exception:
        pass
