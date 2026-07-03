"""
Test del modulo database.py:
- creazione schema da zero con tutte le colonne v1.0 + v2.0
- migrazione automatica da un database v1.0 pre-esistente
- salvataggio e ricostruzione corretta di un Annuncio con tutti i campi
- conversione booleana int <-> bool (bug v1.x corretto)
- funzioni di accesso alle tabelle ausiliarie
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest

# Assicura che i moduli del progetto siano importabili dai test
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import database
from database import Annuncio


class TestDatabaseSchemaFresh(unittest.TestCase):
    """Schema creato ex novo con tutte le colonne v2.0."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_file.close()
        config.DB_PATH = self.db_file.name
        database.init_db()

    def tearDown(self):
        os.unlink(self.db_file.name)

    def test_colonne_v2_presenti(self):
        """Tutte le colonne v2.0 devono essere presenti dopo init_db."""
        with database.get_connection() as conn:
            colonne = {r["name"] for r in conn.execute("PRAGMA table_info(annunci)").fetchall()}
        colonne_v2 = [
            "modello", "categoria", "sottocategoria", "collezione", "edizione",
            "anno", "colore_principale", "colori_secondari", "materiale",
            "condizione", "genere", "collaborazioni", "limited_edition",
            "attributi_estratti_il", "lingua_originale", "titolo_originale",
            "descrizione_originale", "tradotto_il", "testo_ocr", "difetti_rilevati",
            "immagine_sospetta", "punteggio_venditore", "valore_stimato",
            "risparmio_euro", "risparmio_percento", "roi_stimato",
            "profitto_stimato", "margine_percento",
        ]
        for col in colonne_v2:
            self.assertIn(col, colonne, f"Colonna mancante: {col}")

    def test_tabelle_ausiliarie_presenti(self):
        with database.get_connection() as conn:
            tabelle = {r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        for t in ["favorites", "telegram_history", "telegram_sessions",
                  "seen_ads", "ignored_ads", "seller_profiles"]:
            self.assertIn(t, tabelle)


class TestDatabaseMigrazioneV1(unittest.TestCase):
    """Migrazione da un database v1.x senza le colonne v2.0."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_file.close()
        config.DB_PATH = self.db_file.name
        # Crea schema v1.0 manualmente
        conn = sqlite3.connect(self.db_file.name)
        conn.execute("""
            CREATE TABLE annunci (
                id TEXT PRIMARY KEY, piattaforma TEXT NOT NULL,
                titolo TEXT, prezzo REAL, valuta TEXT,
                marca TEXT, taglia TEXT, url TEXT, foto_url TEXT,
                descrizione TEXT, venditore TEXT, keyword_trovata TEXT,
                profilo_ricerca TEXT, timestamp_trovato TEXT,
                prezzo_medio_mercato REAL, is_affare INTEGER,
                punteggio_affidabilita INTEGER, motivo_affidabilita TEXT,
                prezzo_offerta_suggerito REAL, esito_analisi_foto TEXT,
                notificato INTEGER DEFAULT 0, score_finale REAL
            )
        """)
        conn.execute("""INSERT INTO annunci
            (id, piattaforma, titolo, prezzo, valuta, score_finale, notificato)
            VALUES ('v1_001', 'vinted', 'Titolo vecchio', 45.0, 'EUR', 78.5, 1)
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        os.unlink(self.db_file.name)

    def test_migrazione_preserva_dati(self):
        database.init_db()
        with database.get_connection() as conn:
            r = dict(conn.execute("SELECT * FROM annunci WHERE id = 'v1_001'").fetchone())
        self.assertEqual(r["titolo"], "Titolo vecchio")
        self.assertEqual(r["score_finale"], 78.5)
        self.assertIsNone(r["modello"])  # nuova colonna, None per dati pre-esistenti
        self.assertIsNone(r["roi_stimato"])

    def test_migrazione_aggiunge_colonne(self):
        database.init_db()
        with database.get_connection() as conn:
            colonne = {r["name"] for r in conn.execute("PRAGMA table_info(annunci)").fetchall()}
        self.assertIn("modello", colonne)
        self.assertIn("roi_stimato", colonne)
        self.assertIn("limited_edition", colonne)


class TestSalvataggioAnnuncioCompleto(unittest.TestCase):
    """Salvataggio e ricostruzione di un Annuncio con tutti i campi v2.0."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_file.close()
        config.DB_PATH = self.db_file.name
        database.init_db()

    def tearDown(self):
        os.unlink(self.db_file.name)

    def _annuncio_completo(self) -> Annuncio:
        return Annuncio(
            id="test_v2", piattaforma="vinted", titolo="Air Jordan 4 Bred IT",
            prezzo=180.0, valuta="EUR", marca="Nike", taglia="42",
            url="https://x.com/1", foto_url="https://x.com/f.jpg",
            # v2.0 attributi
            modello="Air Jordan 4", categoria="scarpe",
            sottocategoria="sneakers basse", collezione="Retro",
            edizione="Bred Reimagined", anno=2024,
            colore_principale="nero",
            colori_secondari=json.dumps(["rosso", "bianco"]),
            materiale="pelle", condizione="nuovo con cartellino",
            genere="unisex", limited_edition=True,
            attributi_estratti_il="2026-01-01T12:00:00",
            # v2.0 traduzione
            lingua_originale="en",
            titolo_originale="Air Jordan 4 Bred EN",
            tradotto_il="2026-01-01T12:00:00",
            # v2.0 immagine
            testo_ocr="SIZE 42", difetti_rilevati=json.dumps([]),
            immagine_sospetta=False,
            # v2.0 venditore
            punteggio_venditore=88,
            # v2.0 profitto
            valore_stimato=250.0, risparmio_euro=70.0,
            risparmio_percento=28.0, roi_stimato=38.9,
            profitto_stimato=60.0, margine_percento=25.0,
            # score e flags
            score_finale=92.0, notificato=True, is_affare=True,
            punteggio_affidabilita=85,
        )

    def test_salva_e_ricostruisci(self):
        a = self._annuncio_completo()
        database.salva_annuncio(a)
        with database.get_connection() as conn:
            riga = dict(conn.execute("SELECT * FROM annunci WHERE id = 'test_v2'").fetchone())
        r = database.annuncio_da_riga(riga)
        self.assertEqual(r.modello, "Air Jordan 4")
        self.assertEqual(r.edizione, "Bred Reimagined")
        self.assertEqual(r.anno, 2024)
        self.assertEqual(r.roi_stimato, 38.9)
        self.assertEqual(r.profitto_stimato, 60.0)

    def test_booleani_convertiti_correttamente(self):
        """limited_edition, immagine_sospetta, is_affare, notificato devono essere bool Python."""
        a = self._annuncio_completo()
        database.salva_annuncio(a)
        with database.get_connection() as conn:
            riga = dict(conn.execute("SELECT * FROM annunci WHERE id = 'test_v2'").fetchone())
        r = database.annuncio_da_riga(riga)
        self.assertIsInstance(r.is_affare, bool)
        self.assertTrue(r.is_affare)
        self.assertIsInstance(r.notificato, bool)
        self.assertTrue(r.notificato)
        self.assertIsInstance(r.limited_edition, bool)
        self.assertTrue(r.limited_edition)
        self.assertIsInstance(r.immagine_sospetta, bool)
        self.assertFalse(r.immagine_sospetta)

    def test_colori_secondari_json(self):
        a = self._annuncio_completo()
        database.salva_annuncio(a)
        with database.get_connection() as conn:
            riga = dict(conn.execute("SELECT * FROM annunci WHERE id = 'test_v2'").fetchone())
        r = database.annuncio_da_riga(riga)
        colori = json.loads(r.colori_secondari)
        self.assertIsInstance(colori, list)
        self.assertIn("rosso", colori)


class TestFunzioniAusiliarie(unittest.TestCase):
    """Test per le funzioni di accesso a seller_profiles, favorites, ecc."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_file.close()
        config.DB_PATH = self.db_file.name
        database.init_db()

    def tearDown(self):
        os.unlink(self.db_file.name)

    def test_profilo_venditore_salva_e_carica(self):
        database.salva_profilo_venditore("vinted", "user123", {
            "punteggio": 85, "feedback_positivi": 95, "feedback_totali": 100,
            "anzianita_mesi": 18, "numero_vendite": 45,
        })
        profilo = database.carica_profilo_venditore("vinted", "user123")
        self.assertIsNotNone(profilo)
        self.assertEqual(profilo["punteggio"], 85)
        self.assertEqual(profilo["feedback_totali"], 100)

    def test_profilo_venditore_assente(self):
        self.assertIsNone(database.carica_profilo_venditore("vinted", "utente_inesistente"))

    def test_profilo_venditore_recente(self):
        database.salva_profilo_venditore("depop", "seller99", {"punteggio": 70})
        profilo = database.carica_profilo_venditore("depop", "seller99")
        self.assertTrue(database.profilo_venditore_e_recente(profilo, 14))
        self.assertFalse(database.profilo_venditore_e_recente(profilo, 0))

    def test_filtra_ignorati(self):
        database.ignora_pattern("chat1", "marca", "FakeBrand")
        annunci = [
            {"id": "a1", "marca": "Nike", "venditore": "mario"},
            {"id": "a2", "marca": "FakeBrand", "venditore": "luigi"},
            {"id": "a3", "marca": "Adidas", "venditore": "mario"},
        ]
        filtrati = database.filtra_ignorati("chat1", annunci)
        self.assertEqual(len(filtrati), 2)
        self.assertNotIn("a2", [a["id"] for a in filtrati])


if __name__ == "__main__":
    unittest.main(verbosity=2)
