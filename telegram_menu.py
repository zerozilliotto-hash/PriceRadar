"""
Formattazione testuale delle schermate del bot (punto 6 e 17 della
richiesta: menu principale pulito, messaggi ben formattati, emoji
coerenti). Le tastiere (bottoni) associate a questi testi sono in
telegram_buttons.py - questo modulo produce solo il testo del messaggio.
"""

import json
from html import escape

import config
import database


def testo_benvenuto(nome_utente: str) -> str:
    """Messaggio mostrato al comando /start."""
    marketplace_attivi = ", ".join(m for m, attivo in config.MARKETPLACE_ATTIVI.items() if attivo)
    return (
        f"👋 Ciao {_h(nome_utente)}, sono <b>Vinted Hunter</b>.\n\n"
        f"Scrivimi semplicemente cosa stai cercando — ad esempio "
        f"<i>\"nike tech fleece\"</i> o <i>\"jordan 4\"</i> — e cerco subito su "
        f"{marketplace_attivi}.\n\n"
        f"Oppure usa il menu qui sotto. 👇"
    )


def testo_help() -> str:
    """Messaggio del comando /help (punto 13)."""
    return (
        "<b>Come usarmi</b>\n\n"
        "Scrivimi qualsiasi cosa per cercarla subito, niente comandi necessari. "
        "Esempio: <i>maglia adidas</i>\n\n"
        "<b>Comandi disponibili:</b>\n"
        "/start — menu principale\n"
        "/search — avvia una ricerca\n"
        "/history — le tue ultime ricerche\n"
        "/favorites — i tuoi preferiti\n"
        "/stats — statistiche generali\n"
        "/dashboard — link alla dashboard web\n"
        "/settings — impostazioni\n"
        "/help — questo messaggio"
    )


def _emoji_punteggio(valore, soglia_alta, soglia_bassa) -> str:
    """Sceglie un'emoji semaforica in base a un punteggio numerico."""
    if valore is None:
        return "⚪"
    if valore >= soglia_alta:
        return "🟢"
    if valore <= soglia_bassa:
        return "🔴"
    return "🟡"


def _h(valore) -> str:
    """Escape HTML per testi inseriti nei messaggi Telegram."""
    if valore is None:
        return ""
    return escape(str(valore), quote=False)


def _fmt_numero(valore, decimali: int = 2) -> str:
    if valore is None:
        return "N/D"
    try:
        numero = float(valore)
    except (TypeError, ValueError):
        return _h(valore)
    if numero.is_integer():
        return str(int(numero))
    return f"{numero:.{decimali}f}".rstrip("0").rstrip(".")


def _fmt_soldi(valore, valuta: str = "EUR") -> str:
    if valore is None:
        return "N/D"
    return f"{_fmt_numero(valore)} {_h(valuta or 'EUR')}"


def _fmt_percento(valore) -> str:
    if valore is None:
        return "N/D"
    return f"{_fmt_numero(valore, 1)}%"


def annuncio_ha_testo_originale(annuncio: dict) -> bool:
    """True se ha senso mostrare il bottone 'Testo originale'."""
    titolo_originale = annuncio.get("titolo_originale")
    descrizione_originale = annuncio.get("descrizione_originale")
    titolo_corrente = annuncio.get("titolo")
    return bool(
        (titolo_originale and titolo_originale != titolo_corrente)
        or descrizione_originale
        or (annuncio.get("lingua_originale") and annuncio.get("lingua_originale") != "it")
    )


def _lista_difetti(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    try:
        dati = json.loads(raw)
        if isinstance(dati, list):
            return [str(x) for x in dati if x]
    except Exception:
        pass
    return [str(raw)]


def testo_card_annuncio(annuncio: dict, mostra_dettagli_estesi: bool = True) -> str:
    """
    Formatta la card testuale di un singolo annuncio per Telegram.
    v2.0: aggiunge modello riconosciuto, ROI, profitto, colore, difetti.
    Punto 12: foto, traduzione, prezzo, valore, ROI, profitto, colore,
    modello, score, affidabilita'.
    """
    valuta = annuncio.get("valuta") or "EUR"
    titolo = annuncio.get("titolo") or "N/D"
    righe = [f"<b>{_h(titolo)}</b>"]

    if annuncio_ha_testo_originale(annuncio):
        lingua = (annuncio.get("lingua_originale") or "?").upper()
        righe.append(f"🌐 Traduzione IT · originale { _h(lingua) } nel bottone")

    identita = []
    if annuncio.get("marca"):
        identita.append(_h(annuncio["marca"]))
    if annuncio.get("modello") and annuncio["modello"] != annuncio.get("marca"):
        modello = _h(annuncio["modello"])
        if annuncio.get("edizione"):
            modello += f" · {_h(annuncio['edizione'])}"
        identita.append(modello)
    if annuncio.get("collezione"):
        identita.append(_h(annuncio["collezione"]))
    if annuncio.get("limited_edition"):
        identita.append("limited edition")
    if identita:
        righe.append(f"👟 {' · '.join(identita)}")

    attributi = []
    if annuncio.get("categoria"):
        attributi.append(_h(annuncio["categoria"]))
    if annuncio.get("colore_principale"):
        attributi.append(f"colore {_h(annuncio['colore_principale'])}")
    if annuncio.get("taglia"):
        attributi.append(f"taglia {_h(annuncio['taglia'])}")
    if annuncio.get("condizione"):
        attributi.append(_h(annuncio["condizione"]))
    if attributi:
        righe.append(f"🏷 {' · '.join(attributi)}")

    righe.append(f"💰 Prezzo: {_fmt_soldi(annuncio.get('prezzo'), valuta)}")

    if mostra_dettagli_estesi:
        # Stima profitto/ROI (punto 10, 12)
        if annuncio.get("valore_stimato") is not None:
            righe.append(f"📊 Valore stimato: {_fmt_soldi(annuncio.get('valore_stimato'), valuta)}")
        elif annuncio.get("prezzo_medio_mercato") is not None:
            righe.append(f"📊 Valore stimato: {_fmt_soldi(annuncio.get('prezzo_medio_mercato'), valuta)}")

        if annuncio.get("risparmio_euro") is not None:
            righe.append(
                f"📉 Risparmio: {_fmt_soldi(annuncio.get('risparmio_euro'), valuta)} "
                f"({_fmt_percento(annuncio.get('risparmio_percento'))})"
            )

        if annuncio.get("roi_stimato") is not None:
            emoji_roi = "🟢" if annuncio["roi_stimato"] > 20 else ("🟡" if annuncio["roi_stimato"] > 5 else "🔴")
            righe.append(
                f"{emoji_roi} ROI {_fmt_percento(annuncio.get('roi_stimato'))} · "
                f"Profitto {_fmt_soldi(annuncio.get('profitto_stimato'), valuta)} · "
                f"Margine {_fmt_percento(annuncio.get('margine_percento'))}"
            )
        elif annuncio.get("prezzo_medio_mercato"):
            diff_perc = (1 - annuncio["prezzo"] / annuncio["prezzo_medio_mercato"]) * 100
            if diff_perc > 5:
                righe.append(f"📉 {diff_perc:.0f}% sotto il prezzo medio ({_fmt_soldi(annuncio['prezzo_medio_mercato'], valuta)})")
            elif diff_perc < -5:
                righe.append(f"📈 {abs(diff_perc):.0f}% sopra il prezzo medio ({_fmt_soldi(annuncio['prezzo_medio_mercato'], valuta)})")
        else:
            righe.append("📊 Valore/ROI: dati di mercato insufficienti")

        # Affidabilita' e score (punto 12)
        if annuncio.get("punteggio_affidabilita") is not None:
            emoji = _emoji_punteggio(annuncio["punteggio_affidabilita"], 70, 40)
            righe.append(f"{emoji} Affidabilità {annuncio['punteggio_affidabilita']}/100")
            if annuncio.get("motivo_affidabilita") and annuncio["punteggio_affidabilita"] < 70:
                righe.append(f"   {_h(str(annuncio['motivo_affidabilita'])[:180])}")

        if annuncio.get("score_finale") is not None:
            emoji_score = _emoji_punteggio(annuncio["score_finale"], 75, 45)
            righe.append(f"{emoji_score} Score complessivo: {annuncio['score_finale']:.0f}/100")

        if annuncio.get("punteggio_venditore") is not None:
            righe.append(f"👤 Venditore: {_h(annuncio.get('venditore') or 'N/D')} · score {annuncio['punteggio_venditore']}/100")
        elif annuncio.get("venditore"):
            righe.append(f"👤 Venditore: {_h(annuncio.get('venditore'))}")

        # Prezzo offerta (invariato)
        if annuncio.get("prezzo_offerta_suggerito"):
            righe.append(f"💡 Offerta suggerita: {_fmt_soldi(annuncio['prezzo_offerta_suggerito'], valuta)}")

        # Difetti rilevati (v2.0, punto 7)
        difetti = _lista_difetti(annuncio.get("difetti_rilevati"))
        if difetti:
            righe.append(f"⚠️ Difetti: {_h(', '.join(difetti[:3]))}")

        if annuncio.get("esito_analisi_foto") and annuncio.get("esito_analisi_foto") != "nessuna_anomalia_visibile":
            righe.append(f"📸 Foto: {_h(annuncio['esito_analisi_foto'])}")
        if annuncio.get("testo_ocr"):
            righe.append(f"🔎 OCR: {_h(str(annuncio['testo_ocr'])[:120])}")

    contesto = []
    if annuncio.get("piattaforma"):
        contesto.append(_h(annuncio["piattaforma"]))
    if annuncio.get("profilo_ricerca"):
        contesto.append(_h(annuncio["profilo_ricerca"]))
    if contesto:
        righe.append(f"📍 {' · '.join(contesto)}")

    return "\n".join(righe)


def testo_riepilogo_pagina(query: str, pagina: int, totale_pagine: int, n_risultati_totali: int, filtri_descrizione: str) -> str:
    """Intestazione mostrata sopra le card di una pagina di risultati."""
    righe = [f"🔍 Risultati per <b>{_h(query)}</b>"]
    righe.append(f"Pagina {pagina}/{totale_pagine} · {n_risultati_totali} risultati totali")
    if filtri_descrizione != "nessuno":
        righe.append(f"🎛 Filtri attivi: {_h(filtri_descrizione)}")
    return "\n".join(righe)


def testo_nessun_risultato(query: str) -> str:
    return (
        f"😕 Nessun risultato per <b>{_h(query)}</b>.\n\n"
        f"Prova con una parola chiave diversa, o controlla che i marketplace "
        f"siano raggiungibili al momento."
    )


def testo_sezione_affari() -> str:
    """Testo per la sezione 'Ultimi affari' del menu (punto 6)."""
    eccellenti = database.annunci_per_score(limite=config.MAX_AFFARI_ECCELLENTI_PER_CICLO)
    if not eccellenti:
        return "⭐ Non ci sono ancora affari eccellenti rilevati. Torna a controllare piu tardi!"

    righe = ["🔥 <b>Ultimi affari eccellenti</b>\n"]
    for a in eccellenti:
        righe.append(testo_card_annuncio(a, mostra_dettagli_estesi=False))
        righe.append("")
    return "\n".join(righe)


def testo_statistiche() -> str:
    """Testo per la sezione statistiche del menu (punto 6)."""
    with database.get_connection() as conn:
        totale = conn.execute("SELECT COUNT(*) as n FROM annunci").fetchone()["n"]
        affari = conn.execute("SELECT COUNT(*) as n FROM annunci WHERE is_affare = 1").fetchone()["n"]
        per_piattaforma = conn.execute(
            "SELECT piattaforma, COUNT(*) as n FROM annunci GROUP BY piattaforma"
        ).fetchall()
        score_medio = conn.execute(
            "SELECT AVG(score_finale) as media FROM annunci WHERE score_finale IS NOT NULL"
        ).fetchone()["media"]

    righe = ["📈 <b>Statistiche generali</b>\n"]
    righe.append(f"Annunci analizzati: {totale}")
    righe.append(f"Affari rilevati: {affari}")
    if score_medio is not None:
        righe.append(f"Score medio: {score_medio:.0f}/100")
    righe.append("\n<b>Per marketplace:</b>")
    for r in per_piattaforma:
        righe.append(f"  • {_h(r['piattaforma'])}: {r['n']}")

    return "\n".join(righe)


def testo_preferiti_vuoti() -> str:
    return "❤️ Non hai ancora preferiti salvati.\nUsa il bottone ⭐ dopo una ricerca per salvarne uno."


def testo_cronologia_vuota() -> str:
    return "📜 Non hai ancora fatto ricerche.\nScrivimi qualcosa da cercare per iniziare!"


def testo_dashboard() -> str:
    return f"🌐 Apri la dashboard web per un'esperienza completa con filtri e grafici:\n{config.DASHBOARD_URL}"
