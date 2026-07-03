"""
Analisi delle foto di un annuncio tramite un modello vision (Claude).

v2.0 aggiunge:
- analisi_difetti_avanzata: difetti, usura, macchie, scolorimento, pieghe,
  scarpe spaiate, foto duplicate, sfondo sospetto, immagini da catalogo (punto 7)
- ocr_immagine: estrae testo visibile (taglie, etichette, codici - punto 6)

LIMITE IMPORTANTE (invariato dalla v1.0):
Un modello vision generico come Claude NON e' un sistema di autenticazione
prodotti. Non ha un database di confronto con articoli originali. Lo usiamo
solo per rilevare anomalie visive, NON per certificare autenticita'.

Richiede ANTHROPIC_API_KEY in .env.
- analizza_foto: richiede config.ABILITA_ANALISI_FOTO = True
- analisi_difetti_avanzata: richiede anche config.ABILITA_ANALISI_DIFETTI_AVANZATA = True
- ocr_immagine: richiede config.ABILITA_OCR = True

Tutti i metodi sono disabilitati di default: piu' chiamate AI = piu' costo.
"""

import base64
import json
from typing import Optional

import anthropic
import httpx

import config
from database import Annuncio


_client: Optional[anthropic.Anthropic] = None


def _get_client() -> Optional[anthropic.Anthropic]:
    global _client
    if not config.ANTHROPIC_API_KEY:
        return None
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _scarica_immagine_base64(url: str) -> Optional[tuple]:
    """
    Scarica un'immagine e la ritorna come (base64_str, media_type), o None
    se il download fallisce per qualsiasi motivo (timeout, 404, non e'
    un'immagine). Punto 17 (robustezza): nessun crash, solo None.
    """
    try:
        resp = httpx.get(url, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/jpeg")
        if "image" not in content_type:
            content_type = "image/jpeg"
        return base64.b64encode(resp.content).decode("utf-8"), content_type
    except Exception as e:
        print(f"  [WARN] [Foto] Errore nello scaricare '{url[:80]}': {type(e).__name__} - {e}")
        return None


def _chiamata_vision(img_base64: str, media_type: str, prompt: str, max_tokens: int = 400) -> Optional[str]:
    """
    Helper condiviso per le chiamate Claude vision: evita di replicare lo
    stesso blocco try/messages.create in ogni funzione (punto richiesta:
    evita duplicazioni).
    """
    client = _get_client()
    if client is None:
        return None
    try:
        response = client.messages.create(
            model=config.MODELLO_VISION,
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_base64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"  [WARN] [Vision] Errore nella chiamata AI: {type(e).__name__} - {e}")
        return None


def analizza_foto(annuncio: Annuncio) -> Optional[dict]:
    """
    Analisi base (v1.0, invariata): controlla difetti visibili, coerenza con
    la descrizione, e qualita' della foto.

    Ritorna {"esito": str, "note": str} o None se non disponibile.
    "esito" e' una di: nessuna_anomalia_visibile, difetti_visibili,
    incongruenza_con_descrizione, qualita_foto_insufficiente.
    """
    if not config.ABILITA_ANALISI_FOTO:
        return None

    client = _get_client()
    if client is None or not annuncio.foto_url:
        return None

    immagine = _scarica_immagine_base64(annuncio.foto_url)
    if immagine is None:
        return None

    img_base64, media_type = immagine

    prompt = f"""Guarda questa foto di un articolo in vendita su un marketplace di seconda mano.

Titolo dell'annuncio: {annuncio.titolo}
Descrizione: {annuncio.descrizione or "(nessuna descrizione)"}

IMPORTANTE: non puoi determinare con certezza se il prodotto e' autentico o
contraffatto solo da una foto. Concentrati solo su questo:
1. Sono visibili difetti (macchie, strappi, segni di usura, pilling)?
2. Quello che vedi nella foto e' coerente con quanto scritto nel titolo/descrizione?
3. La qualita' della foto e' sufficiente per farsi un'idea (a fuoco, ben illuminata)?

Rispondi SOLO con JSON, senza markdown:
{{"esito": "<nessuna_anomalia_visibile|difetti_visibili|incongruenza_con_descrizione|qualita_foto_insufficiente>", "note": "<spiegazione breve in italiano, massimo 2 frasi, o stringa vuota>"}}"""

    testo_risposta = _chiamata_vision(img_base64, media_type, prompt)
    if testo_risposta is None:
        return None

    try:
        testo_risposta = testo_risposta.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        risultato = json.loads(testo_risposta)
        return {"esito": risultato["esito"], "note": risultato.get("note", "")}
    except Exception as e:
        print(f"  [WARN] [Foto] Errore nel parsing della risposta: {type(e).__name__} - {e}")
        return None


def analisi_difetti_avanzata(annuncio: Annuncio) -> Optional[dict]:
    """
    Analisi approfondita dei difetti (punto 7 della richiesta v2.0).
    Rileva specificamente:
    - Difetti fisici: macchie, strappi, usura, scolorimento, pieghe
    - Difetti per scarpe: spaiate, suola usurata, deformazione
    - Anomalie foto: sfondo sospetto, immagini da catalogo/rubate, foto duplicate
    - Qualita' complessiva delle immagini

    Aggiorna i campi annuncio.difetti_rilevati (JSON list) e
    annuncio.immagine_sospetta (bool) e ritorna un dict riassuntivo.
    Ritorna None se non disponibile/disabilitato.
    """
    if not config.ABILITA_ANALISI_FOTO or not config.ABILITA_ANALISI_DIFETTI_AVANZATA:
        return None

    client = _get_client()
    if client is None or not annuncio.foto_url:
        return None

    immagine = _scarica_immagine_base64(annuncio.foto_url)
    if immagine is None:
        return None

    img_base64, media_type = immagine

    prompt = f"""Analizza questa foto di un articolo in vendita come esperto di reselling.

Titolo: {annuncio.titolo}
Categoria: {annuncio.categoria or "non specificata"}
Condizione dichiarata: {annuncio.condizione or "non specificata"}

Esamina attentamente e identifica SOLO quello che e' chiaramente visibile:

DIFETTI FISICI (per abbigliamento: macchie, strappi, usura, pilling, scolorimento, pieghe permanenti;
per scarpe: suola usurata, deformazione, spaiate, creasing eccessivo):

ANOMALIE FOTO (immagine da catalogo/stock photo, sfondo identico ad altri annunci noti,
foto con watermark di altri siti, qualita' insufficiente per valutare):

Rispondi SOLO con JSON, senza markdown:
{{
  "difetti": ["lista", "dei", "difetti", "visibili"],
  "immagine_sospetta": false,
  "motivo_sospetto": null,
  "punteggio_condizioni": 85,
  "note": "spiegazione breve"
}}

punteggio_condizioni va da 0 (articolo inutilizzabile) a 100 (perfetto/nuovo).
Se non vedi nessun difetto, difetti deve essere lista vuota [].
immagine_sospetta = true solo per anomalie reali e chiare, non per foto di bassa risoluzione."""

    testo_risposta = _chiamata_vision(img_base64, media_type, prompt, max_tokens=500)
    if testo_risposta is None:
        return None

    try:
        testo_risposta = testo_risposta.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        risultato = json.loads(testo_risposta)

        difetti = risultato.get("difetti", [])
        annuncio.difetti_rilevati = json.dumps(difetti, ensure_ascii=False) if isinstance(difetti, list) else None
        annuncio.immagine_sospetta = bool(risultato.get("immagine_sospetta", False))

        return risultato
    except Exception as e:
        print(f"  [WARN] [Difetti] Errore nel parsing della risposta: {type(e).__name__} - {e}")
        return None


def ocr_immagine(annuncio: Annuncio) -> Optional[str]:
    """
    OCR sull'immagine dell'annuncio (punto 6 della richiesta v2.0): estrae
    testo visibile come taglie sull'etichetta, numeri seriali, scritte sul
    prodotto, codici, brand stampati. Il testo estratto viene salvato in
    annuncio.testo_ocr e puo' integrare l'analisi di price_analyzer (es.
    verificare che la taglia sull'etichetta corrisponda a quella dichiarata).

    Disabilitato di default (config.ABILITA_OCR = False) perche' aggiunge
    una chiamata AI extra per ogni immagine.
    """
    if not config.ABILITA_OCR:
        return None

    client = _get_client()
    if client is None or not annuncio.foto_url:
        return None

    immagine = _scarica_immagine_base64(annuncio.foto_url)
    if immagine is None:
        return None

    img_base64, media_type = immagine

    prompt = """Leggi e trascrivi TUTTO il testo visibile in questa immagine, incluso:
- taglie su etichette (es. "SIZE M", "42", "EU 42 US 8.5")
- brand stampati o ricamati sul prodotto
- numeri seriali, codici prodotto, barcode
- istruzioni di lavaggio (simboli + testo)
- scritte sul prodotto (es. "NIKE", "AIR JORDAN", ecc.)
- prezzi o etichette di negozio se visibili

Se non c'e' testo visibile rispondi solo: (nessun testo)
Altrimenti trascrivi il testo esattamente come appare, una riga per ogni elemento distinto."""

    testo = _chiamata_vision(img_base64, media_type, prompt, max_tokens=300)
    if testo and testo != "(nessun testo)":
        annuncio.testo_ocr = testo
    return testo


def analisi_completa_immagine(annuncio: Annuncio) -> dict:
    """
    Esegue tutte le analisi immagine abilitate in un'unica chiamata
    coordinata, aggiorna l'annuncio e ritorna un dict di riepilogo.

    E' il punto di entrata preferito da main.py/telegram per le analisi
    immagine, perche' orchestra automaticamente analizza_foto + difetti
    avanzati + OCR in base ai flag di configurazione (evita che ogni
    chiamante debba sapere quali analisi sono abilitate).
    """
    risultati = {}

    if config.ABILITA_ANALISI_FOTO:
        base = analizza_foto(annuncio)
        if base:
            risultati["base"] = base
            annuncio.esito_analisi_foto = base["esito"]

        if config.ABILITA_ANALISI_DIFETTI_AVANZATA:
            avanzata = analisi_difetti_avanzata(annuncio)
            if avanzata:
                risultati["difetti"] = avanzata

    if config.ABILITA_OCR:
        testo_ocr = ocr_immagine(annuncio)
        if testo_ocr:
            risultati["ocr"] = testo_ocr

    return risultati
