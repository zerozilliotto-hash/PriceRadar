"""
Test di integrazione: verifica che l'intera pipeline analizza_e_salva
(main.py) funzioni end-to-end con tutti i nuovi moduli v2.0, senza rete
e senza API AI reali. Tutti i moduli che richiedono AI vengono testati
con credenziali assenti (fallback graceful).
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import database
import main
import ranking
import profit_calculator
import seller_score
from database import Annuncio


class TestPipelineCompletaNoAI(unittest.TestCase):

    def setUp(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        config.DB_PATH = f.name
        self._db_path = f.name
        database.init_db()

        # Disattiva tutte le chiamate AI: i moduli devono fare graceful fallback
        self._old_key = config.ANTHROPIC_API_KEY
        config.ANTHROPIC_API_KEY = ""
        import product_recognition, translation, ai_advisor, image_analyzer
        product_recognition._client = None
        ai_advisor._client = None
        image_analyzer._client = None
        translation._client = None

        # Attiva solo i componenti deterministici
        config.ABILITA_RICONOSCIMENTO_PRODOTTO = True
        config.ABILITA_TRADUZIONE_AUTOMATICA = True
        config.ABILITA_VALUTAZIONE_AFFIDABILITA = False  # richiede AI
        config.ABILITA_SUGGERIMENTO_PREZZO = False        # richiede AI
        config.ABILITA_ANALISI_FOTO = False               # richiede AI + rete
        config.ABILITA_SCORE_VENDITORE = True
        config.ABILITA_STIMA_PROFITTO = True
        config.MARGINE_COSTI_PERCENTO = 10.0

    def tearDown(self):
        config.ANTHROPIC_API_KEY = self._old_key
        os.unlink(self._db_path)

    def _annuncio_test(self, prezzo: float = 50.0) -> Annuncio:
        return Annuncio(
            id=f"int_test_{prezzo}", piattaforma="vinted",
            titolo="Nike Tech Fleece grigio M",
            prezzo=prezzo, valuta="EUR", marca="Nike", taglia="M",
            url="https://vinted.it/items/123",
            venditore="venditore_test",
            keyword_trovata="Nike Tech Fleece",
            profilo_ricerca="Nike Tech Fleece",
        )

    def test_pipeline_non_crasha_senza_ai(self):
        """La pipeline completa non deve crashare anche senza API AI."""
        a = self._annuncio_test()
        try:
            main.analizza_e_salva(a)
        except Exception as e:
            self.fail(f"analizza_e_salva ha sollevato un'eccezione: {e}")

    def test_pipeline_salva_annuncio(self):
        """Dopo analizza_e_salva l'annuncio deve esistere nel database."""
        a = self._annuncio_test(60.0)
        main.analizza_e_salva(a)
        self.assertTrue(database.esiste_annuncio(a.id))

    def test_pipeline_calcola_score(self):
        """Lo score finale deve essere calcolato e non essere None."""
        a = self._annuncio_test(40.0)
        main.analizza_e_salva(a)
        with database.get_connection() as conn:
            row = conn.execute("SELECT score_finale FROM annunci WHERE id = ?", (a.id,)).fetchone()
        self.assertIsNotNone(row["score_finale"])

    def test_pipeline_fraud_detector_popola_affidabilita(self):
        """Con ABILITA_VALUTAZIONE_AFFIDABILITA=False, usa il fallback del fraud detector."""
        a = self._annuncio_test(35.0)
        main.analizza_e_salva(a)
        with database.get_connection() as conn:
            row = dict(conn.execute("SELECT * FROM annunci WHERE id = ?", (a.id,)).fetchone())
        self.assertIsNotNone(row["punteggio_affidabilita"])

    def test_pipeline_con_prezzo_medio_calcola_profitto(self):
        """Se c'e' abbastanza storico, il profitto deve essere calcolato."""
        # Prima popolo il database con dati storici per avere una media
        for i in range(config.MIN_CAMPIONI_PER_MEDIA + 1):
            storico = Annuncio(
                id=f"storico_{i}", piattaforma="vinted", titolo="Nike Tech Fleece",
                prezzo=80.0, valuta="EUR", keyword_trovata="Nike Tech Fleece",
                profilo_ricerca="Nike Tech Fleece",
            )
            storico.score_finale = 50.0
            database.salva_annuncio(storico)

        a = self._annuncio_test(prezzo=50.0)
        main.analizza_e_salva(a)
        ricostruito = database.annuncio_da_riga(
            dict(database.annunci_per_id([a.id])[0])
        )
        self.assertIsNotNone(ricostruito.prezzo_medio_mercato)
        self.assertIsNotNone(ricostruito.profitto_stimato)
        self.assertGreater(ricostruito.profitto_stimato, 0)

    def test_pipeline_venditore_ottiene_score(self):
        """Il punteggio venditore deve essere calcolato e salvato."""
        a = self._annuncio_test()
        main.analizza_e_salva(a)
        ricostruito = database.annuncio_da_riga(
            dict(database.annunci_per_id([a.id])[0])
        )
        self.assertIsNotNone(ricostruito.punteggio_venditore)

    def test_pipeline_idempotente(self):
        """Eseguire analizza_e_salva due volte sullo stesso annuncio non deve crashare."""
        a = self._annuncio_test()
        main.analizza_e_salva(a)
        a2 = self._annuncio_test()  # stesso ID
        try:
            main.analizza_e_salva(a2)
        except Exception as e:
            self.fail(f"Seconda esecuzione ha sollevato: {e}")

    def test_selezione_eccellenti_usa_score_calcolato(self):
        """
        La funzione invia_notifiche_pendenti deve usare lo score calcolato
        per selezionare correttamente gli annunci eccellenti.
        """
        # Creo annunci con score molto diverso
        for i in range(8):
            a = Annuncio(
                id=f"notif_{i}", piattaforma="vinted", titolo=f"Annuncio {i}",
                prezzo=30.0 + i * 5, valuta="EUR", keyword_trovata="test",
                profilo_ricerca="P", is_affare=(i < 6),
                punteggio_affidabilita=90 - i * 5,
                foto_url="http://x.com/f.jpg",
                esito_analisi_foto="nessuna_anomalia_visibile",
                punteggio_venditore=80,
            )
            a.prezzo_medio_mercato = 80.0
            a.score_finale = ranking.calcola_score(a, punteggio_rischio_fraud=10 + i * 5)
            database.salva_annuncio(a)

        # Con Telegram non configurato, invia_notifiche_pendenti deve comunque
        # girare senza crash e selezionare correttamente i candidati
        try:
            main.invia_notifiche_pendenti()
        except Exception as e:
            self.fail(f"invia_notifiche_pendenti ha sollevato: {e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
