"""
Invio di notifiche Telegram per i nuovi annunci trovati.

Setup richiesto (vedi anche .env.example):
1. Crea un bot con @BotFather su Telegram, ottieni il token
2. Scrivi un messaggio al tuo bot, poi visita
   https://api.telegram.org/bot<TOKEN>/getUpdates per trovare il tuo chat_id
3. Metti entrambi in .env

Questo modulo usa direttamente le chiamate HTTP all'API Telegram (niente
librerie aggiuntive necessarie oltre a httpx, che probabilmente hai già).
"""

from dataclasses import asdict
from typing import Optional

import httpx

import config
from database import Annuncio
import telegram_buttons
import telegram_menu


def _formatta_messaggio(annuncio: Annuncio) -> str:
    """Usa la stessa card v2.0 del bot interattivo per evitare divergenze."""
    return telegram_menu.testo_card_annuncio(asdict(annuncio))


def _reply_markup_annuncio(annuncio: Annuncio) -> dict:
    dati = asdict(annuncio)
    tastiera = telegram_buttons.tastiera_singolo_annuncio(
        annuncio.id,
        annuncio.url,
        ha_originale=telegram_menu.annuncio_ha_testo_originale(dati),
    )
    return tastiera.to_dict()


def _caption_breve(messaggio: str) -> str:
    righe = messaggio.splitlines()
    return "\n".join(righe[:3])[:1000]


def _invia_messaggio_semplice(annuncio: Annuncio) -> bool:
    """Invia il messaggio come solo testo (fallback se la foto non è disponibile/fallisce)."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": _formatta_messaggio(annuncio),
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
        "reply_markup": _reply_markup_annuncio(annuncio),
    }
    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"  [WARN] [Telegram] Errore nell'invio del messaggio: {type(e).__name__} - {e}")
        return False


def _invia_messaggio_con_foto(annuncio: Annuncio) -> bool:
    """
    Invia la foto dell'annuncio con la descrizione come caption. Telegram
    limita le caption a 1024 caratteri: se il messaggio è più lungo,
    Telegram lo rifiuta, quindi in quel caso usiamo solo i primi 1024
    caratteri e basta (l'utente ha comunque il link completo dentro).
    """
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
    caption = _formatta_messaggio(annuncio)
    caption_lunga = len(caption) > 1024

    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "photo": annuncio.foto_url,
        "caption": _caption_breve(caption) if caption_lunga else caption,
        "parse_mode": "HTML",
    }
    if not caption_lunga:
        payload["reply_markup"] = _reply_markup_annuncio(annuncio)

    try:
        resp = httpx.post(url, json=payload, timeout=15.0)
        resp.raise_for_status()
        if caption_lunga:
            return _invia_messaggio_semplice(annuncio)
        return True
    except Exception as e:
        print(f"  [WARN] [Telegram] Errore nell'invio della foto, fallback a testo: {type(e).__name__} - {e}")
        return False


def invia_notifica(annuncio: Annuncio) -> bool:
    """
    Invia una notifica Telegram per l'annuncio. Se l'annuncio ha una foto,
    la invia come immagine con la descrizione come caption (più immediato
    da valutare a colpo d'occhio). Se non c'è foto, o l'invio della foto
    fallisce (es. URL scaduto, immagine non accessibile), usa il messaggio
    di solo testo come fallback.

    Ritorna True se almeno uno dei due tentativi ha successo.
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("  [WARN] [Telegram] Token o chat_id non configurati, notifica saltata.")
        return False

    if annuncio.foto_url and config.INVIA_FOTO_IN_NOTIFICA:
        if _invia_messaggio_con_foto(annuncio):
            return True
        # fallback se la foto non è andata

    return _invia_messaggio_semplice(annuncio)


def invia_messaggio_testo(testo: str) -> bool:
    """Invia un messaggio di testo semplice (es. per riepiloghi o errori)."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = httpx.post(url, json={"chat_id": config.TELEGRAM_CHAT_ID, "text": testo}, timeout=10.0)
        resp.raise_for_status()
        return True
    except Exception:
        return False
