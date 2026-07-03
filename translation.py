"""
Traduzione automatica di titolo e descrizione degli annunci (punto 4).

Design del caching (punto 16): la traduzione viene eseguita una sola volta
e salvata nei campi tradotto_il, lingua_originale, titolo_originale,
descrizione_originale del database. Se un annuncio viene rianalizzato e il
campo tradotto_il e' abbastanza recente (< config.GIORNI_VALIDITA_TRADUZIONE
giorni), la traduzione NON viene rifatta. Questo ha senso perche il testo
originale di un annuncio non cambia dopo la pubblicazione.

Il testo originale viene sempre conservato (titolo_originale,
descrizione_originale) cosi l'utente puo richiederlo in qualsiasi momento
(bottone "Traduzione originale" nel bot Telegram, punto 12).

Richiede ANTHROPIC_API_KEY e config.ABILITA_TRADUZIONE_AUTOMATICA = True.
Se non configurata, l'annuncio torna invariato (nessun crash, punto 17).
"""

import json
from datetime import datetime
from typing import Optional

import anthropic

import config
from database import Annuncio


_client: Optional[anthropic.Anthropic] = None

# Lingue per cui non e' necessaria la traduzione (gia nella lingua target)
_NON_TRADURRE_SE_LINGUA = {config.LINGUA_DEFAULT}


def _get_client() -> Optional[anthropic.Anthropic]:
    global _client
    if not config.ANTHROPIC_API_KEY:
        return None
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _traduzione_e_recente(annuncio: Annuncio) -> bool:
    """
    Verifica se la traduzione salvata e' ancora valida secondo la soglia di
    caching configurata (punto 16): il testo originale di un annuncio non
    cambia quasi mai, quindi una validita' di 90 giorni e' ragionevole.
    """
    if not annuncio.tradotto_il:
        return False
    try:
        tradotto_il = datetime.fromisoformat(annuncio.tradotto_il)
    except ValueError:
        return False
    return (datetime.now() - tradotto_il).days < config.GIORNI_VALIDITA_TRADUZIONE


def _testo_sembra_italiano(testo: str) -> bool:
    """
    Euristica veloce per evitare di chiamare l'AI su annunci gia in
    italiano: se le parole piu comuni della lingua italiana sono presenti,
    probabilmente non serve tradurre. Risparmia chiamate AI (punto 16,
    performance/costo).
    """
    parole_it = {"di", "il", "la", "le", "in", "con", "per", "da", "su",
                 "un", "una", "del", "della", "dei", "che", "non", "taglia",
                 "usato", "nuovo", "ottime", "condizioni", "spedizione"}
    parole_testo = set(testo.lower().split())
    return len(parole_testo & parole_it) >= 3


def traduci_annuncio(annuncio: Annuncio, forza_ricalcolo: bool = False) -> Annuncio:
    """
    Rileva la lingua del titolo/descrizione e, se non e' gia nella lingua
    target (config.LINGUA_DEFAULT, default "it"), traduce titolo e
    descrizione usando Claude. Conserva sempre il testo originale.

    Rispetta il caching (punto 16): se la traduzione e' gia presente e
    recente, non viene rifatta a meno che forza_ricalcolo=True.

    Robustezza (punto 17): qualsiasi errore (timeout, API non disponibile,
    lingua non riconosciuta) lascia l'annuncio con il testo originale -
    mai un crash.
    """
    if not config.ABILITA_TRADUZIONE_AUTOMATICA:
        return annuncio

    # Euristica veloce prima di chiamare l'AI
    testo_principale = annuncio.titolo or ""
    if _testo_sembra_italiano(testo_principale) and not forza_ricalcolo:
        return annuncio

    if not forza_ricalcolo and _traduzione_e_recente(annuncio):
        return annuncio  # gia tradotto di recente

    client = _get_client()
    if client is None:
        return annuncio

    prompt = f"""Sei un traduttore esperto di annunci di marketplace di abbigliamento/calzature.

Titolo dell'annuncio: {annuncio.titolo}
Descrizione: {annuncio.descrizione or "(nessuna descrizione)"}

Compiti:
1. Identifica la lingua originale del testo (codice ISO 639-1, es. "en", "fr", "de", "es", "nl", "it")
2. Se la lingua e' gia "{config.LINGUA_DEFAULT}", metti "gia_in_lingua_target": true e lascia vuoti gli altri campi
3. Altrimenti, traduci titolo e descrizione in {config.LINGUA_DEFAULT.upper()}

Regole di traduzione:
- Mantieni nomi propri di brand e modelli INVARIATI (Nike, Jordan, Adidas, Air Max 90, ecc.)
- Mantieni le taglie INVARIATE (S, M, L, XL, 42, ecc.)
- Traduci tutto il resto naturalmente in italiano
- Se la descrizione e' vuota, lascia descrizione_tradotta come null

Rispondi SOLO con JSON, senza markdown:
{{"lingua_originale": "xx", "gia_in_lingua_target": false, "titolo_tradotto": "...", "descrizione_tradotta": "..."}}"""

    try:
        response = client.messages.create(
            model=config.MODELLO_TESTO,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        testo = response.content[0].text.strip()
        testo = testo.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        risultato = json.loads(testo)

        annuncio.lingua_originale = risultato.get("lingua_originale")
        annuncio.tradotto_il = datetime.now().isoformat(timespec="seconds")

        if not risultato.get("gia_in_lingua_target"):
            # Salva l'originale prima di sovrascrivere
            if annuncio.titolo_originale is None:  # conserva il primissimo originale
                annuncio.titolo_originale = annuncio.titolo
            if annuncio.descrizione_originale is None and annuncio.descrizione:
                annuncio.descrizione_originale = annuncio.descrizione

            titolo_tradotto = risultato.get("titolo_tradotto")
            if titolo_tradotto:
                annuncio.titolo = titolo_tradotto
            if risultato.get("descrizione_tradotta") and annuncio.descrizione:
                annuncio.descrizione = risultato["descrizione_tradotta"]

    except Exception as e:
        print(f"  [WARN] [Traduzione] Errore per '{annuncio.titolo[:50]}': {type(e).__name__} - {e}")
        # L'annuncio resta con il testo originale, nessun crash (punto 17)

    return annuncio


def testo_originale(annuncio: Annuncio) -> str:
    """
    Ritorna il testo originale dell'annuncio (pre-traduzione), usato dal
    bottone 'Traduzione originale' nel bot Telegram (punto 12).
    """
    originale = annuncio.titolo_originale or annuncio.titolo
    desc_orig = annuncio.descrizione_originale or annuncio.descrizione or ""
    lingua = f" [{annuncio.lingua_originale.upper()}]" if annuncio.lingua_originale else ""
    return f"{originale}{lingua}\n{desc_orig}" if desc_orig else f"{originale}{lingua}"
