"""
Test dei moduli che dipendono dall'AI, ma testati SENZA fare chiamate reali
all'API Anthropic: verifichiamo la logica di caching, i fallback in assenza
di credenziali, e la robustezza ai dati malformati.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import database
from database import Annuncio


class TestProductRecognitionCaching(unittest.TestCase):
    """
    Verifica che il caching di product_recognition funzioni senza chiamare l'AI.
    """

    def setUp(self):
        # Forza l'assenza di credenziali AI per questo test
        self._old_key = config.ANTHROPIC_API_KEY
        config.ANTHROPIC_API_KEY = ""
        config.ABILITA_RICONOSCIMENTO_PRODOTTO = True
        config.ABILITA_RICONOSCIMENTO_COLORE = True
        config.GIORNI_VALIDITA_ATTRIBUTI = 30
        import product_recognition as pr
        pr._client = None

    def tearDown(self):
        config.ANTHROPIC_API_KEY = self._old_key

    def test_senza_api_key_nessun_crash(self):
        """Senza API key, riconosci_prodotto ritorna l'annuncio invariato."""
        import product_recognition as pr
        a = Annuncio(id="pr1", piattaforma="vinted", titolo="Air Jordan 4 Bred",
                     prezzo=180.0, valuta="EUR", url="x", keyword_trovata="t", profilo_ricerca="P")
        risultato = pr.riconosci_prodotto(a)
        self.assertIs(risultato, a)  # stesso oggetto ritornato
        self.assertIsNone(a.modello)  # niente modifiche senza AI

    def test_cache_valida_skip(self):
        """Se gli attributi sono stati estratti di recente, non deve fare nulla."""
        import product_recognition as pr
        a = Annuncio(id="pr2", piattaforma="vinted", titolo="Nike",
                     prezzo=50.0, valuta="EUR", url="x", keyword_trovata="t", profilo_ricerca="P",
                     modello="Nike Tech Fleece GIA_RICONOSCIUTO",
                     attributi_estratti_il=datetime.now().isoformat())
        pr.riconosci_prodotto(a)  # non deve sovrascrivere modello
        self.assertEqual(a.modello, "Nike Tech Fleece GIA_RICONOSCIUTO")

    def test_descrizione_prodotto_riconosciuto(self):
        import product_recognition as pr
        a = Annuncio(id="pr3", piattaforma="vinted", titolo="T",
                     prezzo=50.0, valuta="EUR", url="x", keyword_trovata="t", profilo_ricerca="P",
                     modello="Air Jordan 4", edizione="Bred Reimagined",
                     colore_principale="nero", limited_edition=True)
        desc = pr.descrizione_prodotto_riconosciuto(a)
        self.assertIn("Air Jordan 4", desc)
        self.assertIn("Bred Reimagined", desc)
        self.assertIn("limited", desc.lower())

    def test_flags_disattivati(self):
        config.ABILITA_RICONOSCIMENTO_PRODOTTO = False
        config.ABILITA_RICONOSCIMENTO_COLORE = False
        import product_recognition as pr
        a = Annuncio(id="pr4", piattaforma="vinted", titolo="Nike",
                     prezzo=50.0, valuta="EUR", url="x", keyword_trovata="t", profilo_ricerca="P")
        pr.riconosci_prodotto(a)
        self.assertIsNone(a.modello)  # niente fatto con i flag disattivati


class TestTranslationCaching(unittest.TestCase):
    """Logica di caching della traduzione senza API reale."""

    def setUp(self):
        self._old_key = config.ANTHROPIC_API_KEY
        config.ANTHROPIC_API_KEY = ""
        config.ABILITA_TRADUZIONE_AUTOMATICA = True
        config.GIORNI_VALIDITA_TRADUZIONE = 90
        import translation
        translation._client = None

    def tearDown(self):
        config.ANTHROPIC_API_KEY = self._old_key

    def test_senza_api_key_nessun_crash(self):
        import translation
        a = Annuncio(id="t1", piattaforma="vinted", titolo="Nice shoe",
                     prezzo=50.0, valuta="EUR", url="x", keyword_trovata="t", profilo_ricerca="P")
        risultato = translation.traduci_annuncio(a)
        self.assertIs(risultato, a)

    def test_testo_italiano_skip(self):
        """Testo che sembra italiano non deve nemmeno tentare la chiamata AI."""
        import translation
        a = Annuncio(id="t2", piattaforma="vinted",
                     titolo="Felpa in ottime condizioni, usato pochissimo",
                     prezzo=40.0, valuta="EUR", url="x", keyword_trovata="t", profilo_ricerca="P")
        translation.traduci_annuncio(a)
        self.assertIsNone(a.titolo_originale)  # non ha fatto nulla

    def test_cache_valida_skip(self):
        import translation
        a = Annuncio(id="t3", piattaforma="vinted", titolo="Titolo tradotto",
                     prezzo=50.0, valuta="EUR", url="x", keyword_trovata="t", profilo_ricerca="P",
                     titolo_originale="Original title",
                     tradotto_il=datetime.now().isoformat())
        translation.traduci_annuncio(a)
        self.assertEqual(a.titolo_originale, "Original title")  # non modificato

    def test_testo_originale_ritorna_originale(self):
        import translation
        a = Annuncio(id="t4", piattaforma="vinted",
                     titolo="Titolo tradotto in italiano",
                     prezzo=50.0, valuta="EUR", url="x", keyword_trovata="t", profilo_ricerca="P",
                     titolo_originale="Original English Title",
                     lingua_originale="en")
        testo = translation.testo_originale(a)
        self.assertIn("Original English Title", testo)
        self.assertIn("EN", testo)

    def test_disabilitato(self):
        config.ABILITA_TRADUZIONE_AUTOMATICA = False
        import translation
        a = Annuncio(id="t5", piattaforma="vinted", titolo="Something in English",
                     prezzo=50.0, valuta="EUR", url="x", keyword_trovata="t", profilo_ricerca="P")
        translation.traduci_annuncio(a)
        self.assertIsNone(a.lingua_originale)


class TestQueryParserFallback(unittest.TestCase):
    """Fallback del query parser senza AI: deve ritornare la query originale."""

    def setUp(self):
        self._old_key = config.ANTHROPIC_API_KEY
        config.ANTHROPIC_API_KEY = ""
        config.ABILITA_PARSING_QUERY_NATURALE = True
        config.ABILITA_ESPANSIONE_MULTILINGUA = True
        import query_parser
        query_parser._client = None

    def tearDown(self):
        config.ANTHROPIC_API_KEY = self._old_key

    def test_parse_senza_ai_ritorna_query_originale(self):
        import query_parser
        qp = query_parser.parse_query_naturale("Jordan 4 bianca sotto i 150")
        self.assertEqual(qp.query_originale, "Jordan 4 bianca sotto i 150")
        self.assertEqual(qp.keyword_principale, "Air Jordan 4 scarpe bianco")
        self.assertEqual(qp.marca, "Nike")
        self.assertEqual(qp.modello, "Air Jordan 4")
        self.assertEqual(qp.colore, "bianco")
        self.assertEqual(qp.prezzo_max, 150.0)

    def test_espansione_senza_ai_ritorna_solo_originale(self):
        import query_parser
        espanse = query_parser.espandi_keyword_multilingua("maglia adidas")
        self.assertIn("maglia adidas", espanse)
        self.assertEqual(len(espanse), 1)  # senza AI nessuna espansione

    def test_ha_filtri_vuota(self):
        import query_parser
        qp = query_parser.QueryParsata("test query")
        self.assertFalse(qp.ha_filtri())

    def test_ha_filtri_con_prezzo(self):
        import query_parser
        qp = query_parser.QueryParsata("test")
        qp.prezzo_max = 100.0
        self.assertTrue(qp.ha_filtri())

    def test_flags_disattivati(self):
        config.ABILITA_PARSING_QUERY_NATURALE = False
        config.ABILITA_ESPANSIONE_MULTILINGUA = False
        import query_parser
        qp = query_parser.parse_query_naturale("jordan 4")
        self.assertEqual(qp.keyword_principale, "jordan 4")
        espanse = query_parser.espandi_keyword_multilingua("maglia adidas")
        self.assertEqual(espanse, ["maglia adidas"])


class TestReverseImageSearchInterfaccia(unittest.TestCase):
    """Verifica che l'interfaccia astratta funzioni e non colleghi servizi non ufficiali."""

    def test_senza_provider_lista_vuota(self):
        import reverse_image_search
        config.ABILITA_REVERSE_IMAGE_SEARCH = True
        config.REVERSE_IMAGE_SEARCH_PROVIDER = None
        risultati = reverse_image_search.cerca_immagine_simile("http://x.com/img.jpg")
        self.assertEqual(risultati, [])

    def test_disabilitato(self):
        import reverse_image_search
        config.ABILITA_REVERSE_IMAGE_SEARCH = False
        risultati = reverse_image_search.cerca_immagine_simile("http://x.com/img.jpg")
        self.assertEqual(risultati, [])

    def test_provider_sconosciuto_lista_vuota(self):
        import reverse_image_search
        config.ABILITA_REVERSE_IMAGE_SEARCH = True
        config.REVERSE_IMAGE_SEARCH_PROVIDER = "provider_inesistente"
        risultati = reverse_image_search.cerca_immagine_simile("http://x.com/img.jpg")
        self.assertEqual(risultati, [])

    def test_registra_provider_personalizzato(self):
        from reverse_image_search import ReverseImageSearchProvider, registra_provider, _PROVIDER_REGISTRY
        class FakeProvider(ReverseImageSearchProvider):
            def cerca(self, url):
                return [{"url": url, "titolo": "test", "similarita": 0.9, "fonte": "fake"}]
        registra_provider("fake_test", FakeProvider)
        self.assertIn("fake_test", _PROVIDER_REGISTRY)

    def test_provider_non_rsc_tipo_sbagliato(self):
        from reverse_image_search import registra_provider
        with self.assertRaises(TypeError):
            registra_provider("sbagliato", str)  # str non eredita da ReverseImageSearchProvider


if __name__ == "__main__":
    unittest.main(verbosity=2)
