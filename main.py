"""
Entry point principale di Vinted Hunter v2.0.

Pipeline di analisi per ogni annuncio trovato:
1. Prezzi e statistica (sempre attiva)
2. Riconoscimento prodotto/attributi/colori via AI (punto 1, 2, 3)
3. Traduzione automatica (punto 4)
4. Pattern sospetti e fraud detection
5. Valutazione affidabilità AI
6. Score venditore (punto 9)
7. Stima profitto/ROI (punto 10)
8. Analisi foto (base + difetti avanzati + OCR, punti 6, 7)
9. Score finale combinato (ranking.py)
10. Salvataggio database

Compatibilita' con v1.0: ogni step e' opzionale e configurabile da
config.py. Con tutti i flag nuovi disattivati, il comportamento e'
identico alla v1.0.

Esecuzione:
    python3 main.py            # esegue un ciclo singolo e termina
    python3 main.py --loop     # esegue in loop continuo (Ctrl+C per fermare)
"""

import sys
import time
from datetime import datetime

import config
import database
import vinted_client
import ebay_client
import depop_client
import subito_client
import price_analyzer
import fraud_detector
import ai_advisor
import image_analyzer
import telegram_bot
import ranking
import product_recognition
import translation
import seller_score
import profit_calculator
from database import Annuncio


def _cerca_su_marketplace(nome_marketplace: str, keyword: str, prezzo_max, nome_profilo: str) -> list:
    """
    Esegue la ricerca su un singolo marketplace, se attivo in config.
    Centralizza qui la chiamata cosi aggiungere un nuovo marketplace in
    futuro richiede solo una nuova entry in questo dizionario.
    """
    if not config.MARKETPLACE_ATTIVI.get(nome_marketplace, False):
        return []

    funzioni = {
        "vinted": lambda: vinted_client.cerca(keyword, prezzo_max, nome_profilo),
        "ebay": lambda: ebay_client.cerca(keyword, prezzo_max, nome_profilo),
        "depop": lambda: depop_client.cerca(keyword, prezzo_max, nome_profilo),
        "subito": lambda: subito_client.cerca(keyword, prezzo_max, nome_profilo),
    }

    funzione = funzioni.get(nome_marketplace)
    if funzione is None:
        return []

    print(f"  [SEARCH] Cerco '{keyword}' su {nome_marketplace}...")
    risultati = funzione()
    print(f"     -> {len(risultati)} risultati")
    return risultati


def cerca_tutti_i_profili() -> list[Annuncio]:
    """Esegue la ricerca su tutti i marketplace attivi per tutti i profili configurati."""
    nuovi_annunci = []
    marketplace_da_interrogare = [m for m, attivo in config.MARKETPLACE_ATTIVI.items() if attivo]

    for profilo in config.SEARCH_PROFILES:
        nome_profilo = profilo["nome"]
        keywords = profilo["keywords"]
        prezzo_max = profilo.get("prezzo_max")
        taglie_accettate = profilo.get("taglie_accettate")

        print(f"\n[PROFILO] {nome_profilo} (marketplace attivi: {', '.join(marketplace_da_interrogare)})")

        for keyword in keywords:
            risultati_keyword = []
            for nome_marketplace in marketplace_da_interrogare:
                risultati_keyword.extend(
                    _cerca_su_marketplace(nome_marketplace, keyword, prezzo_max, nome_profilo)
                )
                time.sleep(config.DELAY_TRA_RICERCHE_SECONDI)

            for annuncio in risultati_keyword:
                # Filtro taglia, se specificato
                if taglie_accettate and annuncio.taglia not in taglie_accettate:
                    continue
                # Evita duplicati già visti nel database
                if database.esiste_annuncio(annuncio.id):
                    continue
                nuovi_annunci.append(annuncio)

    return nuovi_annunci


def analizza_e_salva(annuncio: Annuncio) -> None:
    """
    Pipeline completa di analisi v2.0. Ogni step e' opzionale (controllato
    da config.py) e gestisce i propri errori internamente (punto 17,
    robustezza) — nessun step fallito blocca i successivi.
    """

    # 1. Riconoscimento prodotto/attributi/colori via AI (punti 1, 2, 3)
    #    Viene eseguito PRIMA dell'analisi prezzi perche' il modello riconosciuto
    #    (es. "Air Jordan 4 Bred Reimagined") e' piu' preciso della keyword
    #    generica per calcolare il prezzo medio di mercato.
    product_recognition.riconosci_prodotto(annuncio)

    # 2. Traduzione automatica titolo/descrizione (punto 4)
    translation.traduci_annuncio(annuncio)

    # 3. Statistica prezzi (sempre attiva, non richiede AI)
    price_analyzer.analizza_prezzo(annuncio)

    # 4. Pattern sospetti espliciti (sempre attivo, non richiede AI)
    segnali_sospetti = fraud_detector.valuta(annuncio)

    # 5. Valutazione affidabilità via AI (opzionale)
    if config.ABILITA_VALUTAZIONE_AFFIDABILITA:
        valutazione = ai_advisor.valuta_affidabilita(annuncio, segnali_sospetti)
        if valutazione:
            annuncio.punteggio_affidabilita = valutazione["punteggio"]
            annuncio.motivo_affidabilita = valutazione["motivo"]
    else:
        annuncio.punteggio_affidabilita = 100 - segnali_sospetti.punteggio_rischio
        annuncio.motivo_affidabilita = (
            "; ".join(segnali_sospetti.motivi) if segnali_sospetti.motivi
            else "Nessun segnale sospetto rilevato"
        )

    # 6. Prezzo di offerta suggerito (opzionale)
    if config.ABILITA_SUGGERIMENTO_PREZZO:
        annuncio.prezzo_offerta_suggerito = ai_advisor.suggerisci_prezzo_offerta(annuncio)

    # 7. Score venditore (punto 9) - caching automatico in database.seller_profiles
    if annuncio.venditore:
        annuncio.punteggio_venditore = seller_score.calcola_score_venditore(
            annuncio.piattaforma, annuncio.venditore
        )

    # 8. Stima profitto/ROI (punto 10) - richiede prezzo_medio_mercato gia calcolato
    profit_calculator.calcola_profitto(annuncio)

    # 9. Analisi foto avanzata (punti 6, 7) - usa image_analyzer.analisi_completa_immagine
    #    che gestisce internamente quali sottoanalisi sono abilitate
    image_analyzer.analisi_completa_immagine(annuncio)

    # 10. Score finale combinato (include ora anche componente venditore)
    annuncio.score_finale = ranking.calcola_score(
        annuncio, punteggio_rischio_fraud=segnali_sospetti.punteggio_rischio
    )

    database.salva_annuncio(annuncio)


def invia_notifiche_pendenti() -> None:
    """
    Nuova logica di notifica (sostituisce l'invio "a pioggia" di tutti gli
    annunci): tra tutti gli annunci non ancora notificati, seleziona solo
    quelli che soddisfano i criteri di "affare eccellente" (vedi
    ranking.e_affare_eccellente), li ordina per score e ne invia al massimo
    config.MAX_AFFARI_ECCELLENTI_PER_CICLO.

    Gli annunci che non rientrano tra gli eccellenti NON vengono inviati
    automaticamente, ma restano nel database con notificato=0: rimangono
    cosi disponibili per essere recuperati dal bot interattivo tramite il
    bottone "Mostra altri" (vedi telegram_search.py), senza necessita di
    una tabella separata.
    """
    da_notificare = database.annunci_da_notificare()
    if not da_notificare:
        print("\n[NOTIFICHE] Nessun nuovo annuncio da valutare per le notifiche.")
        return

    candidati = [database.annuncio_da_riga(row) for row in da_notificare]
    eccellenti = [a for a in candidati if ranking.e_affare_eccellente(a)]
    eccellenti = ranking.classifica_annunci(eccellenti)[: config.MAX_AFFARI_ECCELLENTI_PER_CICLO]

    print(f"\n[NOTIFICHE] {len(candidati)} annunci da valutare, {len(eccellenti)} rientrano tra gli affari eccellenti")

    for annuncio in eccellenti:
        inviato = telegram_bot.invia_notifica(annuncio)
        if inviato:
            database.segna_notificato(annuncio.id)
        time.sleep(0.5)  # piccola pausa per non floodare l'API Telegram

    non_eccellenti = len(candidati) - len(eccellenti)
    if non_eccellenti > 0:
        print(f"   [INFO] {non_eccellenti} altri annunci interessanti restano disponibili "
              f"per il comando 'Ultimi affari' / 'Mostra altri' nel bot Telegram")


def esegui_ciclo() -> None:
    print(f"\n{'='*60}")
    print(f"=== Vinted Hunter — ciclo del {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"{'='*60}")

    nuovi = cerca_tutti_i_profili()
    print(f"\n[OK] {len(nuovi)} nuovi annunci trovati in totale")

    for annuncio in nuovi:
        analizza_e_salva(annuncio)

    invia_notifiche_pendenti()
    print(f"\n=== Ciclo completato ===\n")


def main() -> None:
    database.init_db()

    loop_continuo = "--loop" in sys.argv

    if not loop_continuo:
        esegui_ciclo()
        return

    print(f"[LOOP] Modalita loop attiva: un ciclo ogni {config.INTERVALLO_CICLO_MINUTI} minuti. Ctrl+C per fermare.")
    while True:
        try:
            esegui_ciclo()
        except Exception as e:
            # Non lasciare che un errore imprevisto fermi il loop continuo
            print(f"[ERROR] Errore imprevisto nel ciclo: {type(e).__name__} - {e}")
            telegram_bot.invia_messaggio_testo(f"⚠️ Vinted Hunter ha incontrato un errore: {e}")

        time.sleep(config.INTERVALLO_CICLO_MINUTI * 60)


if __name__ == "__main__":
    main()
