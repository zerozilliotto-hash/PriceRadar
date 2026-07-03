"""
Test dei moduli di calcolo deterministici (nessuna chiamata AI, testabili
sempre e velocemente): ranking, profit_calculator, seller_score.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import database
import profit_calculator
import ranking
import seller_score
from database import Annuncio


def _setup_db(test_case):
    """Helper: crea un database temporaneo per ogni test."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    config.DB_PATH = f.name
    database.init_db()
    test_case._db_path = f.name


def _teardown_db(test_case):
    os.unlink(test_case._db_path)


class TestRanking(unittest.TestCase):

    def _annuncio(self, **kwargs) -> Annuncio:
        defaults = dict(
            id="r1", piattaforma="vinted", titolo="Test", prezzo=50.0, valuta="EUR",
            url="x", keyword_trovata="t", profilo_ricerca="P",
            prezzo_medio_mercato=100.0, is_affare=True,
            punteggio_affidabilita=80, foto_url="http://x.com/f.jpg",
            esito_analisi_foto="nessuna_anomalia_visibile", punteggio_venditore=70,
        )
        defaults.update(kwargs)
        return Annuncio(**defaults)

    def test_score_eccellente_alto(self):
        """Annuncio con tutti i segnali positivi deve avere score alto."""
        a = self._annuncio(punteggio_affidabilita=90, punteggio_venditore=85, piattaforma="ebay")
        score = ranking.calcola_score(a, punteggio_rischio_fraud=5)
        self.assertGreater(score, 70)

    def test_score_sospetto_basso(self):
        """Annuncio con fraud alto e affidabilita' bassa deve avere score basso."""
        a = self._annuncio(punteggio_affidabilita=20, punteggio_venditore=30, foto_url=None)
        score = ranking.calcola_score(a, punteggio_rischio_fraud=85)
        self.assertLess(score, 60)

    def test_prezzo_non_affare_penalizza(self):
        """Prezzo sopra la media penalizza il componente prezzo."""
        a_caro = self._annuncio(prezzo=150.0, prezzo_medio_mercato=100.0)
        a_affare = self._annuncio(prezzo=30.0, prezzo_medio_mercato=100.0)
        score_caro = ranking.calcola_score(a_caro)
        score_affare = ranking.calcola_score(a_affare)
        self.assertGreater(score_affare, score_caro)

    def test_classifica_ordine(self):
        a1 = self._annuncio(id="c1", punteggio_affidabilita=90)
        a1.score_finale = ranking.calcola_score(a1, punteggio_rischio_fraud=5)
        a2 = self._annuncio(id="c2", punteggio_affidabilita=40, foto_url=None)
        a2.score_finale = ranking.calcola_score(a2, punteggio_rischio_fraud=70)
        a3 = self._annuncio(id="c3", punteggio_affidabilita=70)
        a3.score_finale = ranking.calcola_score(a3, punteggio_rischio_fraud=30)
        classificati = ranking.classifica_annunci([a2, a3, a1])
        self.assertEqual(classificati[0].id, "c1")  # il migliore deve venire prima
        self.assertEqual(classificati[-1].id, "c2")  # il peggiore alla fine

    def test_e_affare_eccellente_tutti_i_criteri(self):
        """Deve passare TUTTI i criteri, non solo lo score."""
        a = self._annuncio(punteggio_affidabilita=90, punteggio_venditore=85)
        a.score_finale = 92.0
        a.is_affare = True
        self.assertTrue(ranking.e_affare_eccellente(a))

    def test_e_affare_eccellente_no_se_is_affare_false(self):
        """Score alto ma non affare: non deve risultare eccellente."""
        a = self._annuncio(is_affare=False, punteggio_affidabilita=90)
        a.score_finale = 92.0
        self.assertFalse(ranking.e_affare_eccellente(a))

    def test_e_affare_eccellente_no_se_affidabilita_bassa(self):
        """Score alto ma affidabilita' sotto soglia: non eccellente."""
        a = self._annuncio(punteggio_affidabilita=30)
        a.score_finale = 80.0
        a.is_affare = True
        self.assertFalse(ranking.e_affare_eccellente(a))

    def test_score_senza_dati_prezzo(self):
        """Se prezzo_medio_mercato e' None, componente prezzo usa valore neutro (50)."""
        a = self._annuncio(prezzo_medio_mercato=None, is_affare=None)
        score = ranking.calcola_score(a)
        # Con prezzo neutro (50) lo score deve essere compreso in un range ragionevole
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 100)

    def test_somma_pesi_corretta(self):
        """I pesi configurati devono sommare a 1.0."""
        somma = sum(config.PESI_SCORE.values())
        self.assertAlmostEqual(somma, 1.0, places=3)


class TestProfitCalculator(unittest.TestCase):

    def _annuncio_con_prezzi(self, prezzo: float, media: float) -> Annuncio:
        return Annuncio(
            id="p1", piattaforma="vinted", titolo="T", prezzo=prezzo, valuta="EUR",
            url="x", keyword_trovata="t", profilo_ricerca="P",
            prezzo_medio_mercato=media,
        )

    def test_calcolo_base(self):
        """Test base: prezzo 50, media 100, margine costi 10%."""
        config.MARGINE_COSTI_PERCENTO = 10.0
        config.ABILITA_STIMA_PROFITTO = True
        a = self._annuncio_con_prezzi(50.0, 100.0)
        profit_calculator.calcola_profitto(a)
        self.assertEqual(a.valore_stimato, 100.0)
        self.assertEqual(a.risparmio_euro, 50.0)
        self.assertEqual(a.risparmio_percento, 50.0)
        self.assertAlmostEqual(a.profitto_stimato, 45.0, places=1)  # 50 - (50*10%) = 45
        self.assertIsNotNone(a.roi_stimato)
        self.assertIsNotNone(a.margine_percento)

    def test_nessun_calcolo_senza_media(self):
        """Senza prezzo_medio_mercato, nessun campo deve essere popolato."""
        config.ABILITA_STIMA_PROFITTO = True
        a = self._annuncio_con_prezzi(50.0, None)
        profit_calculator.calcola_profitto(a)
        self.assertIsNone(a.valore_stimato)
        self.assertIsNone(a.roi_stimato)

    def test_disabilitato(self):
        config.ABILITA_STIMA_PROFITTO = False
        a = self._annuncio_con_prezzi(50.0, 100.0)
        profit_calculator.calcola_profitto(a)
        self.assertIsNone(a.valore_stimato)

    def test_prezzo_sopra_media_risparmio_negativo(self):
        """Se il prezzo e' sopra la media, il risparmio e' negativo."""
        config.ABILITA_STIMA_PROFITTO = True
        config.MARGINE_COSTI_PERCENTO = 10.0
        a = self._annuncio_con_prezzi(130.0, 100.0)
        profit_calculator.calcola_profitto(a)
        self.assertLess(a.risparmio_euro, 0)
        self.assertLess(a.risparmio_percento, 0)

    def test_riepilogo_profitto_stringa(self):
        config.ABILITA_STIMA_PROFITTO = True
        config.MARGINE_COSTI_PERCENTO = 10.0
        a = self._annuncio_con_prezzi(50.0, 100.0)
        profit_calculator.calcola_profitto(a)
        testo = profit_calculator.riepilogo_profitto(a)
        self.assertIn("ROI", testo)
        self.assertIn("Profitto", testo)

    def test_riepilogo_senza_dati(self):
        a = self._annuncio_con_prezzi(50.0, None)
        testo = profit_calculator.riepilogo_profitto(a)
        self.assertIn("insufficienti", testo)


class TestSellerScore(unittest.TestCase):

    def setUp(self):
        _setup_db(self)
        config.ABILITA_SCORE_VENDITORE = True
        config.GIORNI_VALIDITA_PROFILO_VENDITORE = 14

    def tearDown(self):
        _teardown_db(self)

    def test_score_con_feedback_perfetto(self):
        score = seller_score.calcola_score_venditore(
            "vinted", "topvendor",
            dati_extra={"feedback_positivi": 200, "feedback_totali": 200,
                        "anzianita_mesi": 36, "numero_vendite": 200}
        )
        self.assertGreater(score, 70)

    def test_score_senza_dati(self):
        """Senza dati extra usa solo coerenza (neutra = 50) -> score neutro."""
        score = seller_score.calcola_score_venditore("depop", "nuovo_venditore")
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 100)

    def test_score_disabilitato(self):
        config.ABILITA_SCORE_VENDITORE = False
        score = seller_score.calcola_score_venditore("vinted", "chiunque")
        self.assertEqual(score, 50)

    def test_caching(self):
        """Il punteggio calcolato deve essere salvato nel database."""
        seller_score.calcola_score_venditore("vinted", "vendcache", dati_extra={"punteggio": 80})
        profilo = database.carica_profilo_venditore("vinted", "vendcache")
        self.assertIsNotNone(profilo)

    def test_coerenza_annunci_stessa_categoria(self):
        """Un venditore con tutti annunci nella stessa categoria deve avere coerenza alta."""
        for i in range(5):
            a = Annuncio(
                id=f"coe_{i}", piattaforma="vinted", titolo=f"Scarpa {i}",
                prezzo=50.0, valuta="EUR", url="x", keyword_trovata="t",
                profilo_ricerca="P", venditore="coerente", categoria="scarpe",
            )
            database.salva_annuncio(a)
        coerenza = seller_score._calcola_coerenza_annunci("vinted", "coerente")
        self.assertGreater(coerenza, 60)

    def test_coerenza_annunci_categorie_diverse(self):
        """Un venditore con categorie molto diverse deve avere coerenza bassa."""
        categorie = ["scarpe", "elettronica", "libri", "giocattoli", "cucina"]
        for i, cat in enumerate(categorie):
            a = Annuncio(
                id=f"inc_{i}", piattaforma="vinted", titolo=f"Prod {i}",
                prezzo=30.0, valuta="EUR", url="x", keyword_trovata="t",
                profilo_ricerca="P", venditore="incoerente", categoria=cat,
            )
            database.salva_annuncio(a)
        coerenza = seller_score._calcola_coerenza_annunci("vinted", "incoerente")
        self.assertLess(coerenza, 40)


if __name__ == "__main__":
    unittest.main(verbosity=2)
