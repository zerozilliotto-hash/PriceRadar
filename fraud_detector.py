"""
Rilevamento di annunci potenzialmente sospetti, tramite regole semplici ed
esplicite (NON intelligenza artificiale: qui usiamo pattern matching
trasparente, così sai sempre esattamente perché un annuncio è stato
segnalato).

IMPORTANTE: questo è un aiuto, non un verdetto. Un punteggio "sospetto" non
significa che il venditore sia in malafede - può semplicemente avere scritto
poco. Usa questi segnali come un elemento in più nella tua valutazione, non
come unico criterio per scartare un annuncio.
"""

from dataclasses import dataclass

from database import Annuncio


# Frasi che spesso accompagnano vendite poco trasparenti o a rischio
FRASI_SOSPETTE = [
    "pagamento fuori app",
    "contattami su whatsapp",
    "contattami su telegram",
    "no resi",
    "vendita urgente",
    "scambio con paypal amici",
    "fuori piattaforma",
]

MARCHE_FREQUENTEMENTE_CONTRAFFATTE = [
    "nike", "adidas", "stone island", "supreme", "gucci",
    "louis vuitton", "moncler", "off-white", "yeezy",
]


@dataclass
class ValutazioneSospetto:
    punteggio_rischio: int       # 0-100, più alto = più motivi di attenzione
    motivi: list[str]


def valuta(annuncio: Annuncio) -> ValutazioneSospetto:
    motivi = []
    punteggio = 0

    descrizione = (annuncio.descrizione or "").lower()
    titolo = (annuncio.titolo or "").lower()
    testo = f"{titolo} {descrizione}"

    # 1. Frasi che suggeriscono di uscire dalla piattaforma (perdita di
    #    protezione acquirente)
    for frase in FRASI_SOSPETTE:
        if frase in testo:
            punteggio += 25
            motivi.append(f"Contiene la frase sospetta: \"{frase}\"")

    # 2. Descrizione estremamente corta per un prodotto di marca importante
    marca_nota = any(m in testo for m in MARCHE_FREQUENTEMENTE_CONTRAFFATTE)
    if marca_nota and len(descrizione.strip()) < 15:
        punteggio += 15
        motivi.append("Descrizione molto breve per un prodotto di marca conosciuta")

    # 3. Prezzo sospettosamente basso rispetto a un prodotto di marca
    #    (qui usiamo solo una soglia grezza come ulteriore segnale, il
    #    confronto serio è già fatto da price_analyzer.py)
    if marca_nota and annuncio.prezzo > 0 and annuncio.prezzo < 10:
        punteggio += 20
        motivi.append("Prezzo molto basso per una marca generalmente più costosa")

    # 4. Nessuna foto
    if not annuncio.foto_url:
        punteggio += 10
        motivi.append("Annuncio senza foto")

    punteggio = min(punteggio, 100)
    return ValutazioneSospetto(punteggio_rischio=punteggio, motivi=motivi)
