"""
Dashboard web v2.0 per Vinted Hunter.

Nuovi endpoint v2.0:
- /api/annunci: filtri estesi (marca, modello, colore, taglia, roi_min,
  score_min, ricerca testuale) + ordinamento per roi/profitto/score
- /api/statistiche_globali: riepilogo globale con distribuzione marketplace,
  score medio, migliori ROI
- /api/trend/<profilo>: andamento prezzi nel tempo per un profilo

Retrocompatibilita': tutti gli endpoint v1.0 restano identici.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, jsonify

import database
import config

app = Flask(__name__)


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/annunci")
def api_annunci():
    """
    Endpoint annunci con filtri estesi v2.0.
    Parametri query string:
    - profilo, solo_affari, piattaforma, ordina (invariati da v1.0)
    - marca, modello, colore, taglia (nuovi filtri attributo v2.0)
    - roi_min: ROI stimato minimo (es. "15" per >= 15%)
    - score_min: score finale minimo (es. "70")
    - q: ricerca testuale su titolo, marca, modello
    - solo_tradotti: "1" per mostrare solo annunci tradotti
    """
    profilo = request.args.get("profilo")
    solo_affari = request.args.get("solo_affari") == "1"
    piattaforma = request.args.get("piattaforma")
    ordina = request.args.get("ordina", "recenti")
    marca = request.args.get("marca")
    modello = request.args.get("modello")
    colore = request.args.get("colore")
    taglia = request.args.get("taglia")
    roi_min = request.args.get("roi_min", type=float)
    score_min = request.args.get("score_min", type=float)
    q = request.args.get("q", "").strip()
    solo_tradotti = request.args.get("solo_tradotti") == "1"

    query = "SELECT * FROM annunci WHERE 1=1"
    params = []

    if profilo:
        query += " AND profilo_ricerca = ?"
        params.append(profilo)
    if solo_affari:
        query += " AND is_affare = 1"
    if piattaforma:
        query += " AND piattaforma = ?"
        params.append(piattaforma)
    if marca:
        query += " AND marca LIKE ?"
        params.append(f"%{marca}%")
    if modello:
        query += " AND modello LIKE ?"
        params.append(f"%{modello}%")
    if colore:
        query += " AND (colore_principale LIKE ? OR colori_secondari LIKE ?)"
        params.extend([f"%{colore}%", f"%{colore}%"])
    if taglia:
        query += " AND taglia = ?"
        params.append(taglia)
    if roi_min is not None:
        query += " AND roi_stimato >= ?"
        params.append(roi_min)
    if score_min is not None:
        query += " AND score_finale >= ?"
        params.append(score_min)
    if q:
        query += " AND (titolo LIKE ? OR marca LIKE ? OR modello LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if solo_tradotti:
        query += " AND titolo_originale IS NOT NULL"

    ordine_map = {
        "recenti": "timestamp_trovato DESC",
        "prezzo_asc": "prezzo ASC",
        "affidabilita": "punteggio_affidabilita DESC",
        "score": "score_finale DESC",
        "roi": "roi_stimato DESC",
        "profitto": "profitto_stimato DESC",
    }
    query += f" ORDER BY {ordine_map.get(ordina, ordine_map['recenti'])}"

    with database.get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return jsonify([dict(r) for r in rows])


@app.route("/api/profili")
def api_profili():
    """Ritorna la lista dei profili disponibili con conteggi e statistiche di base."""
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT profilo_ricerca, COUNT(*) as totale, "
            "SUM(CASE WHEN is_affare = 1 THEN 1 ELSE 0 END) as affari, "
            "AVG(score_finale) as score_medio, "
            "AVG(roi_stimato) as roi_medio "
            "FROM annunci GROUP BY profilo_ricerca"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/statistiche/<profilo>")
def api_statistiche_profilo(profilo):
    """Statistiche di prezzo per un profilo specifico."""
    stats = database.prezzo_medio_per_profilo(profilo)
    if stats is None:
        return jsonify({"disponibile": False, "messaggio": f"Servono almeno {config.MIN_CAMPIONI_PER_MEDIA} annunci storici"})
    stats["disponibile"] = True
    return jsonify(stats)


@app.route("/api/statistiche_globali")
def api_statistiche_globali():
    """
    Statistiche globali v2.0: distribuzione marketplace, score medio,
    migliori ROI, annunci per categoria, tendenze.
    """
    with database.get_connection() as conn:
        totale = conn.execute("SELECT COUNT(*) as n FROM annunci").fetchone()["n"]
        affari = conn.execute("SELECT COUNT(*) as n FROM annunci WHERE is_affare = 1").fetchone()["n"]

        per_piattaforma = {r["piattaforma"]: r["n"] for r in conn.execute(
            "SELECT piattaforma, COUNT(*) as n FROM annunci GROUP BY piattaforma"
        ).fetchall()}

        per_categoria = {r["categoria"]: r["n"] for r in conn.execute(
            "SELECT categoria, COUNT(*) as n FROM annunci WHERE categoria IS NOT NULL GROUP BY categoria ORDER BY n DESC LIMIT 10"
        ).fetchall()}

        migliori_roi = [dict(r) for r in conn.execute(
            "SELECT id, titolo, prezzo, roi_stimato, profitto_stimato, score_finale, url "
            "FROM annunci WHERE roi_stimato IS NOT NULL ORDER BY roi_stimato DESC LIMIT 10"
        ).fetchall()]

        score_medio = conn.execute(
            "SELECT AVG(score_finale) as media FROM annunci WHERE score_finale IS NOT NULL"
        ).fetchone()["media"]

        roi_medio = conn.execute(
            "SELECT AVG(roi_stimato) as media FROM annunci WHERE roi_stimato IS NOT NULL"
        ).fetchone()["media"]

    return jsonify({
        "totale_annunci": totale,
        "totale_affari": affari,
        "per_piattaforma": per_piattaforma,
        "per_categoria": per_categoria,
        "migliori_roi": migliori_roi,
        "score_medio": round(score_medio, 1) if score_medio else None,
        "roi_medio": round(roi_medio, 1) if roi_medio else None,
    })


@app.route("/api/trend/<profilo>")
def api_trend(profilo):
    """
    Andamento prezzi nel tempo per un profilo: utile per il grafico
    storico prezzi nella dashboard (punto 11 v2.0).
    """
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT date(timestamp_trovato) as giorno, AVG(prezzo) as prezzo_medio, "
            "COUNT(*) as volume "
            "FROM annunci WHERE profilo_ricerca = ? AND prezzo > 0 "
            "GROUP BY giorno ORDER BY giorno",
            (profilo,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    database.init_db()
    print("🌐 Dashboard v2.0 disponibile su http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
