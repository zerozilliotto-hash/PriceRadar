"""
Parser di query in linguaggio naturale e espansione multilingua (punti 5
e 13 della richiesta v2.0).

QUERY NATURALE (punto 13): l'utente puo scrivere al bot Telegram cose come
"Cerco una Jordan 4 bianca sotto i 170 euro" e il sistema estrae
automaticamente: marca=Nike, modello=Air Jordan 4, colore=bianco,
prezzo_max=170. Questo sostituisce il vecchio sistema "testo libero =
keyword" con un approccio strutturato.

ESPANSIONE MULTILINGUA (punto 5): "maglia adidas" diventa anche "Adidas
shirt", "Adidas jersey", "T-shirt Adidas", ecc. cosi i marketplace in
lingua diversa dall'italiano mostrano comunque risultati pertinenti.

Retrocompatibilita': telegram_handlers.py chiama gia' esegui_ricerca_libera
passando la query testuale - questo modulo si inserisce nella pipeline
PRIMA della ricerca, espandendo la query senza modificare il contratto
dell'interfaccia esistente.

Richiede ANTHROPIC_API_KEY. Se non configurata, il parser ritorna la query
originale invariata come unica keyword (comportamento v1.0).
"""

import json
import re
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


class QueryParsata:
    """
    Risultato del parsing di una query in linguaggio naturale.
    Tutti i campi possono essere None se non riconosciuti nella query.
    """
    __slots__ = (
        "query_originale", "marca", "modello", "colore", "taglia",
        "prezzo_max", "categoria", "marketplace", "keyword_principale",
        "keyword_espanse",
    )

    def __init__(self, query_originale: str):
        self.query_originale = query_originale
        self.marca: Optional[str] = None
        self.modello: Optional[str] = None
        self.colore: Optional[str] = None
        self.taglia: Optional[str] = None
        self.prezzo_max: Optional[float] = None
        self.categoria: Optional[str] = None
        self.marketplace: Optional[str] = None
        # keyword_principale: la query piu precisa da usare come query di ricerca
        self.keyword_principale: str = query_originale
        # keyword_espanse: versioni multilingua della query per i marketplace
        self.keyword_espanse: list = [query_originale]

    def ha_filtri(self) -> bool:
        """True se sono stati estratti almeno un attributo strutturato dalla query."""
        return any([self.marca, self.modello, self.colore, self.taglia,
                    self.prezzo_max, self.categoria, self.marketplace])

    def __repr__(self) -> str:
        campi = {k: getattr(self, k) for k in self.__slots__ if getattr(self, k) is not None}
        return f"QueryParsata({campi})"


_COLORI = {
    "nero": ("nero", "nera", "neri", "nere", "black"),
    "bianco": ("bianco", "bianca", "bianchi", "bianche", "white"),
    "grigio": ("grigio", "grigia", "grigi", "grigie", "grey", "gray"),
    "verde": ("verde", "verdi", "green"),
    "rosso": ("rosso", "rossa", "rossi", "rosse", "red"),
    "blu": ("blu", "blue"),
    "azzurro": ("azzurro", "azzurra", "azzurri", "azzurre"),
    "marrone": ("marrone", "marroni", "brown"),
    "beige": ("beige", "cream", "crema"),
    "rosa": ("rosa", "pink"),
    "viola": ("viola", "purple"),
    "giallo": ("giallo", "gialla", "gialli", "gialle", "yellow"),
    "arancione": ("arancione", "orange"),
}

_BRAND_ALIASES = {
    "Nike": ("nike",),
    "Adidas": ("adidas",),
    "Stone Island": ("stone island",),
    "Moncler": ("moncler",),
    "CP Company": ("cp company", "c.p. company", "c p company"),
    "Supreme": ("supreme",),
    "Palace": ("palace",),
    "New Balance": ("new balance",),
    "Asics": ("asics",),
    "Stussy": ("stussy", "stüssy"),
    "Carhartt": ("carhartt",),
    "The North Face": ("north face", "tnf", "the north face"),
}

_CATEGORIE = {
    "felpe": ("felpa", "felpe", "hoodie", "sweatshirt"),
    "magliette": ("maglia", "maglietta", "t-shirt", "shirt", "jersey"),
    "scarpe": ("scarpa", "scarpe", "sneaker", "sneakers", "jordan", "dunk"),
    "giacche": ("giacca", "giacche", "giubbotto", "jacket", "coat"),
    "pantaloni": ("pantalone", "pantaloni", "pants", "trousers"),
}


def _contiene_alias(testo: str, alias: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(a)}\b", testo) for a in alias)


def _parse_query_euristica(query_testo: str) -> QueryParsata:
    """
    Parser locale, economico e sempre disponibile. Non sostituisce l'AI,
    ma copre le richieste piu comuni del bot anche senza API key.
    """
    risultato = QueryParsata(query_testo)
    testo = query_testo.lower()

    for marketplace in ("vinted", "ebay", "depop", "subito"):
        if re.search(rf"\b{marketplace}\b", testo):
            risultato.marketplace = marketplace
            break

    prezzo_match = re.search(
        r"(?:sotto|massimo|max|entro|meno di|under|fino a)\s*(?:i|gli|le|a)?\s*(\d+(?:[,.]\d+)?)",
        testo,
    ) or re.search(r"\b(\d+(?:[,.]\d+)?)\s*(?:€|euro)\b", testo)
    if prezzo_match:
        try:
            risultato.prezzo_max = float(prezzo_match.group(1).replace(",", "."))
        except ValueError:
            pass

    taglia_match = re.search(r"\b(?:taglia|tg|size)\s*([a-z]{1,3}|\d{2})\b", testo)
    if not taglia_match:
        taglia_match = re.search(r"\b(xs|s|m|l|xl|xxl|xxxl|3[5-9]|4[0-9]|50)\b", testo)
    if taglia_match:
        risultato.taglia = taglia_match.group(1).upper()

    for colore, alias in _COLORI.items():
        if _contiene_alias(testo, alias):
            risultato.colore = colore
            break

    for brand, alias in _BRAND_ALIASES.items():
        if _contiene_alias(testo, alias):
            risultato.marca = brand
            break

    if re.search(r"\b(?:air\s*)?jordan\s*4\b", testo):
        risultato.marca = "Nike"
        risultato.modello = "Air Jordan 4"
        risultato.categoria = "scarpe"
    elif re.search(r"\b(?:nike\s*)?tech(?:\s*fleece)?\b", testo):
        risultato.marca = "Nike"
        risultato.modello = "Nike Tech Fleece"
        risultato.categoria = risultato.categoria or "felpe"
    elif re.search(r"\bdunk\s*low\b", testo):
        risultato.marca = risultato.marca or "Nike"
        risultato.modello = "Nike Dunk Low"
        risultato.categoria = "scarpe"

    for categoria, alias in _CATEGORIE.items():
        if _contiene_alias(testo, alias):
            risultato.categoria = categoria
            break

    parti_keyword = []
    if risultato.modello:
        parti_keyword.append(risultato.modello)
    elif risultato.marca:
        parti_keyword.append(risultato.marca)
    if risultato.categoria and risultato.categoria not in " ".join(parti_keyword).lower():
        parti_keyword.append(risultato.categoria)
    if risultato.colore:
        parti_keyword.append(risultato.colore)

    if parti_keyword:
        risultato.keyword_principale = " ".join(parti_keyword)
        risultato.keyword_espanse = [risultato.keyword_principale]

    return risultato


def parse_query_naturale(query_testo: str) -> QueryParsata:
    """
    Interpreta una query in linguaggio naturale estraendo marca, modello,
    colore, taglia, prezzo e categoria (punto 13). Se il parsing AI non e'
    disponibile o fallisce, ritorna la query originale invariata.

    Esempi:
    "Cerco una Jordan 4 bianca sotto i 170 euro" →
        marca="Nike", modello="Air Jordan 4", colore="bianco", prezzo_max=170.0

    "maglia adidas nera taglia M" →
        marca="Adidas", categoria="magliette", colore="nero", taglia="M"
    """
    if not config.ABILITA_PARSING_QUERY_NATURALE:
        return QueryParsata(query_testo)

    risultato = _parse_query_euristica(query_testo)

    client = _get_client()
    if client is None:
        return risultato

    prompt = f"""Sei un assistente esperto di reselling di abbigliamento e calzature.

L'utente ha scritto questa richiesta di ricerca: "{query_testo}"

Estrai gli attributi strutturati, usando SOLO le informazioni presenti nella frase:
- marca: brand del prodotto (es. "Nike", "Adidas", "Stone Island")
- modello: modello specifico (es. "Air Jordan 4", "Tech Fleece", "Dunk Low")
- colore: colore cercato (es. "bianco", "nero", "verde militare")
- taglia: taglia cercata (es. "M", "42", "XL")
- prezzo_max: prezzo massimo in euro come numero (es. 170, 80.50)
- categoria: tipo di prodotto (es. "scarpe", "felpe", "giacche", "magliette")
- marketplace: marketplace specifico se menzionato (es. "vinted", "ebay", "depop")
- keyword_principale: la keyword di ricerca piu precisa da passare ai marketplace
  (es. se l'utente cerca "jordan 4 bianca", usa "Air Jordan 4 white" o "Jordan 4 Bianca")

Rispondi SOLO con JSON, senza markdown:
{{"marca": null, "modello": null, "colore": null, "taglia": null, "prezzo_max": null, "categoria": null, "marketplace": null, "keyword_principale": "..."}}

Usa null per campi non presenti nella query. keyword_principale deve essere sempre valorizzata."""

    try:
        response = client.messages.create(
            model=config.MODELLO_TESTO,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        testo = response.content[0].text.strip()
        testo = testo.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        dati = json.loads(testo)

        risultato.marca = dati.get("marca") or risultato.marca
        risultato.modello = dati.get("modello") or risultato.modello
        risultato.colore = dati.get("colore") or risultato.colore
        risultato.taglia = dati.get("taglia") or risultato.taglia
        risultato.marketplace = dati.get("marketplace") or risultato.marketplace
        risultato.categoria = dati.get("categoria") or risultato.categoria

        prezzo_max = dati.get("prezzo_max")
        if isinstance(prezzo_max, (int, float)):
            risultato.prezzo_max = float(prezzo_max)

        kw_principale = dati.get("keyword_principale")
        if kw_principale:
            risultato.keyword_principale = kw_principale

    except Exception as e:
        print(f"  [WARN] [Query parser] Errore nel parsing di '{query_testo}': {type(e).__name__} - {e}")

    return risultato


def espandi_keyword_multilingua(keyword: str) -> list[str]:
    """
    Espande una keyword nelle principali lingue dei marketplace (punto 5).
    Es. "maglia adidas" → ["maglia adidas", "Adidas shirt", "Adidas jersey",
    "T-shirt Adidas", "Adidas Trikot", "Adidas maillot"].

    La keyword originale e' sempre la prima della lista. Se l'espansione
    fallisce (AI non configurata, errore), ritorna solo la keyword originale
    (comportamento v1.0, nessun crash - punto 17).
    """
    if not config.ABILITA_ESPANSIONE_MULTILINGUA:
        return [keyword]

    client = _get_client()
    if client is None:
        return [keyword]

    lingue_target = [l for l in config.LINGUE_SUPPORTATE if l != "it"]

    prompt = f"""Sei un esperto di moda e reselling con conoscenza di tutti i marketplace europei.

Keyword di ricerca originale (in italiano): "{keyword}"

Genera versioni equivalenti di questa keyword nelle seguenti lingue:
{', '.join(lingue_target)}

Regole:
- Mantieni nomi di brand, modelli e codici prodotto INVARIATI (Nike, Jordan, Air Max 90, ecc.)
- Traduci solo le parole comuni (colori, capi di abbigliamento, aggettivi)
- Genera al massimo 2-3 varianti per lingua (le piu comuni nei marketplace)
- Includi solo varianti realmente usate nelle ricerche, non traduzioni letterali forzate

Rispondi SOLO con JSON: {{"keyword_originale": "...", "espansioni": ["...", "..."]}}
Le espansioni devono essere una lista piatta di stringhe, senza raggruppamento per lingua."""

    try:
        response = client.messages.create(
            model=config.MODELLO_TESTO,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        testo = response.content[0].text.strip()
        testo = testo.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        dati = json.loads(testo)
        espansioni = dati.get("espansioni", [])
        if isinstance(espansioni, list):
            # La keyword originale prima, senza duplicati
            tutte = [keyword] + [e for e in espansioni if e and e.lower() != keyword.lower()]
            return tutte[:10]  # limite ragionevole: non piu' di 10 keyword per ricerca
    except Exception as e:
        print(f"  [WARN] [Espansione multilingua] Errore per '{keyword}': {type(e).__name__} - {e}")

    return [keyword]


def crea_profilo_temporaneo_da_query(
    query_parsata: QueryParsata,
    profilo_nome_base: str,
) -> dict:
    """
    Costruisce un 'profilo ricerca temporaneo' (con struttura simile ai
    profili in config.SEARCH_PROFILES) a partire da una query parsata, cosi
    telegram_search.py puo riusare la stessa pipeline senza modifiche.

    Il profilo usa le keyword espanse multilingua se l'espansione e' attiva,
    e i filtri estratti dal parser (prezzo_max, ecc.) se presenti.
    """
    keyword_espanse = espandi_keyword_multilingua(query_parsata.keyword_principale)

    return {
        "nome": profilo_nome_base,
        "keywords": keyword_espanse,
        "prezzo_max": query_parsata.prezzo_max,
        "taglie_accettate": [query_parsata.taglia] if query_parsata.taglia else None,
        "_filtro_colore": query_parsata.colore,
        "_filtro_marketplace": query_parsata.marketplace,
    }
