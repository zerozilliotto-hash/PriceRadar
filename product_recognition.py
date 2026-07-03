"""
Riconoscimento intelligente del prodotto a partire da titolo e descrizione
di un annuncio, usando Claude per estrarre attributi strutturati invece di
affidarsi solo al matching testuale delle keyword (punto 1, 2, 3 della
richiesta v2.0).

Esempio concreto: una ricerca per "Jordan 4" deve riconoscere che un
annuncio intitolato "Air Jordan 4 Retro Bred Reimagined GS" appartiene al
modello "Air Jordan 4", edizione "Bred Reimagined" - cosi il prezzo medio di
mercato puo essere calcolato sul modello/edizione specifico invece che su
tutta la generica famiglia "Jordan 4" (dove il prezzo varia moltissimo tra
un colorway raro e uno comune).

DESIGN: una singola chiamata AI per annuncio estrae TUTTI gli attributi in
un colpo solo (marca, modello, categoria, colore, materiale, condizione,
ecc.) invece di chiamate separate per ogni attributo - piu efficiente in
termini di costo/tempo (punto 16, performance) e piu coerente (l'AI vede il
quadro completo invece di giudicare ogni attributo isolatamente).

CACHING (punto 16): il risultato dell'estrazione viene salvato nel database
(campo attributi_estratti_il) - se un annuncio viene rianalizzato entro
config.GIORNI_VALIDITA_ATTRIBUTI, l'estrazione non viene rifatta.

Richiede ANTHROPIC_API_KEY. Se non configurata, o se config.
ABILITA_RICONOSCIMENTO_PRODOTTO/ABILITA_RICONOSCIMENTO_COLORE sono
disattivati, le funzioni ritornano senza modificare l'annuncio (nessun
errore, comportamento equivalente alla v1.0).
"""

import json
from datetime import datetime
from typing import Optional

import anthropic

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


def _attributi_sono_recenti(annuncio: Annuncio) -> bool:
    """Verifica se gli attributi gia estratti sono abbastanza recenti da poter essere riusati (punto 16)."""
    if not annuncio.attributi_estratti_il:
        return False
    try:
        estratti_il = datetime.fromisoformat(annuncio.attributi_estratti_il)
    except ValueError:
        return False
    return (datetime.now() - estratti_il).days < config.GIORNI_VALIDITA_ATTRIBUTI


def _costruisci_prompt(annuncio: Annuncio) -> str:
    """Costruisce il prompt di estrazione attributi, riusato sia per riconoscimento prodotto sia colore."""
    return f"""Analizza questo annuncio di un marketplace di seconda mano e estrai gli attributi del prodotto in modo strutturato.

Titolo: {annuncio.titolo}
Descrizione: {annuncio.descrizione or "(nessuna descrizione)"}
Marca dichiarata nei filtri del marketplace (puo essere assente o sbagliata): {annuncio.marca or "non specificata"}

Estrai questi attributi, usando SOLO le informazioni presenti nel testo (non inventare nulla che non sia ragionevolmente deducibile):
- marca: il brand del prodotto
- modello: il nome specifico del modello/linea (es. "Air Jordan 4", "Tech Fleece", non solo "Jordan" o "Nike")
- categoria: categoria generale (es. "scarpe", "felpe", "giacche", "magliette")
- sottocategoria: piu specifica se deducibile (es. "sneakers basse", "felpa con cappuccio")
- collezione: linea/collezione se menzionata (es. "Retro", "Originals")
- edizione: nome specifico del colorway/edizione se menzionato (es. "Bred Reimagined", "Military Black", "Frozen Moments")
- anno: anno di rilascio se deducibile dal testo, altrimenti null
- colore_principale: il colore dominante del prodotto
- colori_secondari: lista di altri colori presenti, anche vuota
- materiale: materiale principale se menzionato (es. "pelle", "cotone", "poliestere")
- condizione: stato dichiarato (es. "nuovo con cartellino", "usato buone condizioni", "usato visibili segni di usura")
- genere: "uomo", "donna", "unisex", "bambino" se deducibile, altrimenti null
- collaborazioni: eventuale collaborazione/collab menzionata (es. "Travis Scott x Jordan"), altrimenti null
- limited_edition: true se il testo indica esplicitamente un'edizione limitata, altrimenti false

Rispondi SOLO con un oggetto JSON valido, senza markdown, esattamente con queste chiavi:
{{"marca": "...", "modello": "...", "categoria": "...", "sottocategoria": "...", "collezione": "...", "edizione": "...", "anno": null, "colore_principale": "...", "colori_secondari": ["..."], "materiale": "...", "condizione": "...", "genere": "...", "collaborazioni": null, "limited_edition": false}}

Usa null (non la stringa "null") per qualsiasi attributo non deducibile dal testo. Non inventare informazioni assenti."""


def _applica_risultato(annuncio: Annuncio, risultato: dict) -> None:
    """Applica il dict estratto dall'AI ai campi dell'oggetto Annuncio, con validazione minima dei tipi."""
    annuncio.marca = risultato.get("marca") or annuncio.marca  # non sovrascrivere se l'AI non trova nulla di nuovo
    annuncio.modello = risultato.get("modello")
    annuncio.categoria = risultato.get("categoria")
    annuncio.sottocategoria = risultato.get("sottocategoria")
    annuncio.collezione = risultato.get("collezione")
    annuncio.edizione = risultato.get("edizione")

    anno = risultato.get("anno")
    annuncio.anno = int(anno) if isinstance(anno, (int, float)) else None

    annuncio.colore_principale = risultato.get("colore_principale")
    colori_secondari = risultato.get("colori_secondari")
    annuncio.colori_secondari = json.dumps(colori_secondari, ensure_ascii=False) if isinstance(colori_secondari, list) else None

    annuncio.materiale = risultato.get("materiale")
    annuncio.condizione = risultato.get("condizione")
    annuncio.genere = risultato.get("genere")
    annuncio.collaborazioni = risultato.get("collaborazioni")
    annuncio.limited_edition = bool(risultato.get("limited_edition", False))
    annuncio.attributi_estratti_il = datetime.now().isoformat(timespec="seconds")


def riconosci_prodotto(annuncio: Annuncio, forza_ricalcolo: bool = False) -> Annuncio:
    """
    Estrae marca, modello, categoria, colore e tutti gli altri attributi
    strutturati da un annuncio (punto 1, 2, 3). Modifica l'annuncio sul
    posto e lo ritorna.

    Rispetta il caching (punto 16): se gli attributi sono gia stati
    estratti di recente, non rifa la chiamata AI a meno che
    forza_ricalcolo=True.

    Se config.ABILITA_RICONOSCIMENTO_PRODOTTO e config.
    ABILITA_RICONOSCIMENTO_COLORE sono entrambi disattivati, o l'AI non e
    configurata, l'annuncio torna invariato (nessun errore).
    """
    if not config.ABILITA_RICONOSCIMENTO_PRODOTTO and not config.ABILITA_RICONOSCIMENTO_COLORE:
        return annuncio

    if not forza_ricalcolo and _attributi_sono_recenti(annuncio):
        return annuncio  # cache valida, niente da fare (punto 16)

    client = _get_client()
    if client is None:
        return annuncio

    prompt = _costruisci_prompt(annuncio)

    try:
        response = client.messages.create(
            model=config.MODELLO_TESTO,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        testo = response.content[0].text.strip()
        testo = testo.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        risultato = json.loads(testo)
        _applica_risultato(annuncio, risultato)
    except Exception as e:
        print(f"  [WARN] [Riconoscimento prodotto] Errore per '{annuncio.titolo[:50]}': {type(e).__name__} - {e}")
        # In caso di errore l'annuncio resta con gli attributi None/precedenti,
        # nessun crash (punto 17, robustezza)

    return annuncio


def descrizione_prodotto_riconosciuto(annuncio: Annuncio) -> str:
    """
    Costruisce una stringa leggibile che riassume cosa e' stato riconosciuto
    per un annuncio, utile per i log e per i messaggi Telegram/dashboard.
    """
    parti = []
    if annuncio.modello:
        parti.append(annuncio.modello)
    if annuncio.edizione:
        parti.append(annuncio.edizione)
    if annuncio.colore_principale:
        parti.append(annuncio.colore_principale)
    if annuncio.limited_edition:
        parti.append("(limited edition)")
    return " · ".join(parti) if parti else "attributi non ancora riconosciuti"
