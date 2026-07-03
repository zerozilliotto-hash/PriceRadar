import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vinted_client


class FakeScraper:
    def __init__(self, items):
        self.items = items
        self.params = None

    def search(self, params):
        self.params = params
        return self.items


class TestVintedClientMapping(unittest.TestCase):

    def tearDown(self):
        vinted_client._scraper = None

    def test_cerca_mappa_foto_dict_e_attributi_vinted(self):
        item = SimpleNamespace(
            id=123,
            title="Nike Tech Fleece grigia M",
            price=50.0,
            currency="EUR",
            brand_title="Nike",
            size_title="M",
            url="https://www.vinted.it/items/123",
            photo={
                "url": "https://images.vinted.net/listing.jpg",
                "full_size_url": "https://images.vinted.net/full.jpg",
            },
            photos=[],
            description="Felpa in ottime condizioni",
            user=SimpleNamespace(login="venditore_test"),
            status="Ottime condizioni",
            color1="Grigio",
        )
        fake_scraper = FakeScraper([item])
        vinted_client._scraper = fake_scraper

        risultati = vinted_client.cerca("Nike Tech", 80.0, "profilo_test")

        self.assertEqual(len(risultati), 1)
        annuncio = risultati[0]
        self.assertEqual(annuncio.id, "vinted_123")
        self.assertEqual(annuncio.foto_url, "https://images.vinted.net/full.jpg")
        self.assertEqual(annuncio.condizione, "Ottime condizioni")
        self.assertEqual(annuncio.colore_principale, "Grigio")
        self.assertEqual(fake_scraper.params["price_to"], 80.0)

    def test_estrai_url_foto_fallback_su_lista_photos(self):
        item = SimpleNamespace(
            photo=None,
            photos=[
                SimpleNamespace(url="https://images.vinted.net/thumb.jpg", full_size_url=None),
                SimpleNamespace(url="https://images.vinted.net/second.jpg", full_size_url=None),
            ],
        )

        self.assertEqual(
            vinted_client._estrai_url_foto(item),
            "https://images.vinted.net/thumb.jpg",
        )

    def test_cerca_ritorna_lista_vuota_se_cookie_vinted_fallisce(self):
        original_get_scraper = vinted_client._get_scraper

        def raise_cookie_error():
            raise RuntimeError("Cannot fetch session cookie from https://www.vinted.it")

        try:
            vinted_client._get_scraper = raise_cookie_error
            vinted_client._scraper = object()

            risultati = vinted_client.cerca("Jordan 4", 170.0, "profilo_test")
        finally:
            vinted_client._get_scraper = original_get_scraper

        self.assertEqual(risultati, [])
        self.assertIsNone(vinted_client._scraper)


if __name__ == "__main__":
    unittest.main(verbosity=2)
