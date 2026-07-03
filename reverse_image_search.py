"""
Interfaccia astratta per il reverse image search (punto 8 della richiesta
v2.0).

IMPORTANTE - citazione diretta dal punto 8 della richiesta:
  "Predisporre un modulo opzionale per il confronto immagini.
   Il modulo deve essere facilmente collegabile in futuro a servizi esterni.
   Non implementare servizi non ufficiali.
   Creare interfaccia astratta."

Questo modulo implementa esattamente questa specifica: definisce l'interfaccia
(la classe astratta ReverseImageSearchProvider e la funzione pubblica
cerca_immagine_simile) ma NON collega nessun provider reale. Lo fa
deliberatamente perche i servizi di reverse image search non ufficiali
(reverse.photos, TinEye via scraping, ecc.) violano i termini d'uso, mentre
quelli ufficiali (Google Vision API, AWS Rekognition) richiedono credenziali
e accordi commerciali che l'utente deve procurarsi autonomamente.

Quando vorrai collegare un provider reale:
1. Crea una classe che eredita da ReverseImageSearchProvider
2. Implementa il metodo cerca(url_immagine)
3. Registra la classe in _PROVIDER_REGISTRY
4. Imposta config.REVERSE_IMAGE_SEARCH_PROVIDER = "nome_del_tuo_provider"

Esempio (per Google Vision API, se hai le credenziali):
    class GoogleVisionProvider(ReverseImageSearchProvider):
        def cerca(self, url_immagine: str) -> list[dict]:
            # ... implementa qui chiamata a googleapis.com/vision/v1/images:annotate
            pass
    
    _PROVIDER_REGISTRY["google_vision"] = GoogleVisionProvider
"""

from abc import ABC, abstractmethod
from typing import Optional

import config


class ReverseImageSearchProvider(ABC):
    """
    Contratto che ogni implementazione di reverse image search deve
    soddisfare. Il metodo cerca() riceve l'URL dell'immagine da analizzare
    e ritorna una lista di risultati (dict con almeno 'url', 'titolo',
    'similarita'), o lista vuota se nessun risultato trovato.
    """

    @abstractmethod
    def cerca(self, url_immagine: str) -> list[dict]:
        """
        Cerca immagini simili a quella all'URL fornito.

        Ritorna una lista di dict, ciascuno con:
        - url: URL dell'immagine simile trovata
        - titolo: titolo/descrizione della pagina/prodotto trovato
        - similarita: float 0-1 (1 = identica, 0 = completamente diversa)
        - fonte: nome del servizio/sito da cui viene il risultato
        """
        ...


# Registry dei provider disponibili. Vuoto di default (nessun provider
# non ufficiale), pronto per essere esteso dall'utente con provider ufficiali.
_PROVIDER_REGISTRY: dict[str, type] = {}


def _get_provider() -> Optional[ReverseImageSearchProvider]:
    """
    Istanzia e ritorna il provider configurato, o None se non configurato/
    non disponibile. Separato da cerca_immagine_simile per testabilita'.
    """
    nome_provider = config.REVERSE_IMAGE_SEARCH_PROVIDER
    if not nome_provider:
        return None
    classe = _PROVIDER_REGISTRY.get(nome_provider)
    if classe is None:
        print(f"  [WARN] [Reverse Image Search] Provider '{nome_provider}' non trovato nel registry. "
              f"Provider disponibili: {list(_PROVIDER_REGISTRY.keys()) or ['nessuno']}")
        return None
    return classe()


def cerca_immagine_simile(url_immagine: str) -> list[dict]:
    """
    Punto di accesso pubblico al reverse image search. Ritorna una lista di
    immagini simili trovate (potenzialmente vuota), o lista vuota se il
    modulo non e' abilitato/configurato.

    La funzione e' robusta (punto 17): qualsiasi errore del provider esterno
    viene catturato e logghato, mai propagato all'esterno.
    """
    if not config.ABILITA_REVERSE_IMAGE_SEARCH:
        return []

    provider = _get_provider()
    if provider is None:
        return []

    try:
        risultati = provider.cerca(url_immagine)
        return risultati if isinstance(risultati, list) else []
    except Exception as e:
        print(f"  [WARN] [Reverse Image Search] Errore nella ricerca per '{url_immagine[:80]}': "
              f"{type(e).__name__} - {e}")
        return []


def registra_provider(nome: str, classe: type) -> None:
    """
    Registra un nuovo provider di reverse image search. Da chiamare nel
    proprio codice di configurazione prima di avviare il sistema.

    Esempio:
        from reverse_image_search import registra_provider, ReverseImageSearchProvider

        class MioProvider(ReverseImageSearchProvider):
            def cerca(self, url): ...

        registra_provider("mio_provider", MioProvider)
        # poi in config.py: REVERSE_IMAGE_SEARCH_PROVIDER = "mio_provider"
    """
    if not issubclass(classe, ReverseImageSearchProvider):
        raise TypeError(f"{classe.__name__} deve ereditare da ReverseImageSearchProvider")
    _PROVIDER_REGISTRY[nome] = classe
    print(f"  [OK] [Reverse Image Search] Provider '{nome}' registrato correttamente.")
