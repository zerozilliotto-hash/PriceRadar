"""
Dashboard web - API e servizio Flask
Espone dati del database come API JSON per la dashboard moderna
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import sqlite3
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__, template_folder='templates')
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'annunci.db')

def get_db_connection():
    """Connessione al database SQLite"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def dict_from_row(row):
    """Converte sqlite3.Row a dict"""
    if row is None:
        return None
    return dict(row)

def parse_json_field(value):
    """Parse JSON field in modo sicuro"""
    if not value:
        return None
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (json.JSONDecodeError, TypeError):
        return None

@app.route('/')
def dashboard():
    """Pagina dashboard HTML"""
    return render_template('dashboard.html')

@app.route('/api/products', methods=['GET'])
def get_products():
    """
    GET /api/products
    Ritorna lista prodotti con filtri opzionali
    
    Query params:
    - marketplace: vinted, ebay, depop, subito
    - min_price, max_price
    - min_roi
    - brand
    - color
    - sort: roi, price, seller_score (default: roi desc)
    - limit: massimo 100 (default: 50)
    """
    try:
        conn = get_db_connection()
        
        # Parametri filtro
        marketplace = request.args.get('marketplace', '').lower()
        min_price = request.args.get('min_price', type=float, default=0)
        max_price = request.args.get('max_price', type=float, default=float('inf'))
        min_roi = request.args.get('min_roi', type=float, default=0)
        brand = request.args.get('brand', '').lower()
        color = request.args.get('color', '').lower()
        sort = request.args.get('sort', 'roi')
        limit = min(request.args.get('limit', type=int, default=50), 100)
        
        # Query base
        query = "SELECT * FROM annunci WHERE 1=1"
        params = []
        
        # Filtri
        if marketplace:
            query += " AND LOWER(marketplace) = ?"
            params.append(marketplace)
        
        if min_price > 0:
            query += " AND prezzo >= ?"
            params.append(min_price)
        
        if max_price < float('inf'):
            query += " AND prezzo <= ?"
            params.append(max_price)
        
        if min_roi > 0:
            query += " AND COALESCE(roi_stimato, 0) >= ?"
            params.append(min_roi)
        
        if brand:
            query += " AND LOWER(COALESCE(brand, '')) LIKE ?"
            params.append(f'%{brand}%')
        
        if color:
            query += " AND LOWER(COALESCE(colore_principale, '')) = ?"
            params.append(color)
        
        # Sort
        sort_map = {
            'roi': 'COALESCE(roi_stimato, 0) DESC',
            'price': 'prezzo ASC',
            'seller_score': 'COALESCE(score_venditore, 0) DESC',
            'profit': 'COALESCE(profitto_stimato, 0) DESC',
            'recent': 'data_acquisizione DESC'
        }
        order_by = sort_map.get(sort, 'COALESCE(roi_stimato, 0) DESC')
        query += f" ORDER BY {order_by} LIMIT ?"
        params.append(limit)
        
        # Esecuzione
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        products = []
        for row in rows:
            product = dict(row)
            
            # Parse JSON fields
            product['attributi'] = parse_json_field(product.get('attributi'))
            product['difetti_rilevati'] = parse_json_field(product.get('difetti_rilevati'))
            
            # Assicura campi numerici
            numeric_fields = ['prezzo', 'valore_stimato', 'risparmio_euro', 'risparmio_percento',
                            'profitto_stimato', 'roi_stimato', 'margine_percento', 'score_venditore',
                            'affidabilita']
            for field in numeric_fields:
                if field in product and product[field] is not None:
                    product[field] = float(product[field])
                else:
                    product[field] = 0.0
            
            products.append(product)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(products),
            'products': products
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """
    GET /api/statistics
    Statistiche globali
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Statistiche generali
        cursor.execute("""
            SELECT 
                COUNT(*) as total_listings,
                COUNT(DISTINCT marketplace) as total_marketplaces,
                COUNT(DISTINCT venditore) as total_sellers,
                AVG(prezzo) as avg_price,
                MIN(prezzo) as min_price,
                MAX(prezzo) as max_price,
                AVG(COALESCE(roi_stimato, 0)) as avg_roi,
                SUM(CASE WHEN COALESCE(roi_stimato, 0) > 20 THEN 1 ELSE 0 END) as high_roi_count,
                AVG(COALESCE(score_venditore, 0)) as avg_seller_score
            FROM annunci
        """)
        stats = dict(cursor.fetchone())
        
        # Distribuzione per marketplace
        cursor.execute("""
            SELECT marketplace, COUNT(*) as count, AVG(COALESCE(roi_stimato, 0)) as avg_roi
            FROM annunci
            GROUP BY marketplace
            ORDER BY count DESC
        """)
        marketplace_stats = [dict(row) for row in cursor.fetchall()]
        
        # Categorie top
        cursor.execute("""
            SELECT category, COUNT(*) as count, AVG(COALESCE(roi_stimato, 0)) as avg_roi
            FROM annunci
            WHERE category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
            LIMIT 10
        """)
        category_stats = [dict(row) for row in cursor.fetchall()]
        
        # Brand top
        cursor.execute("""
            SELECT brand, COUNT(*) as count, AVG(COALESCE(roi_stimato, 0)) as avg_roi
            FROM annunci
            WHERE brand IS NOT NULL
            GROUP BY brand
            ORDER BY count DESC
            LIMIT 10
        """)
        brand_stats = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        # Formattazione numerica
        for field in ['avg_price', 'min_price', 'max_price', 'avg_roi', 'avg_seller_score']:
            if stats[field] is not None:
                stats[field] = round(stats[field], 2)
        
        return jsonify({
            'success': True,
            'global': stats,
            'by_marketplace': marketplace_stats,
            'top_categories': category_stats,
            'top_brands': brand_stats
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/trending', methods=['GET'])
def get_trending():
    """
    GET /api/trending
    Trend ultimi giorni
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        days = request.args.get('days', type=int, default=7)
        since = datetime.now() - timedelta(days=days)
        
        cursor.execute("""
            SELECT 
                DATE(data_acquisizione) as day,
                COUNT(*) as new_listings,
                AVG(COALESCE(roi_stimato, 0)) as avg_roi,
                AVG(prezzo) as avg_price
            FROM annunci
            WHERE data_acquisizione >= ?
            GROUP BY DATE(data_acquisizione)
            ORDER BY day ASC
        """, (since.isoformat(),))
        
        trend = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({
            'success': True,
            'days': days,
            'trend': trend
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/product/<product_id>', methods=['GET'])
def get_product_detail(product_id):
    """
    GET /api/product/<id>
    Dettagli completi prodotto
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM annunci WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({'success': False, 'error': 'Prodotto non trovato'}), 404
        
        product = dict(row)
        product['attributi'] = parse_json_field(product.get('attributi'))
        product['difetti_rilevati'] = parse_json_field(product.get('difetti_rilevati'))
        
        return jsonify({'success': True, 'product': product})
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/search', methods=['POST'])
def search():
    """
    POST /api/search
    Ricerca full-text
    """
    try:
        data = request.get_json()
        query = data.get('query', '')
        
        if not query or len(query) < 2:
            return jsonify({'success': False, 'error': 'Query troppo breve'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        search_term = f'%{query}%'
        cursor.execute("""
            SELECT * FROM annunci
            WHERE 
                LOWER(titolo) LIKE LOWER(?) OR
                LOWER(descrizione) LIKE LOWER(?) OR
                LOWER(brand) LIKE LOWER(?) OR
                LOWER(modello) LIKE LOWER(?)
            ORDER BY COALESCE(roi_stimato, 0) DESC
            LIMIT 50
        """, (search_term, search_term, search_term, search_term))
        
        rows = cursor.fetchall()
        conn.close()
        
        products = [dict(row) for row in rows]
        
        return jsonify({
            'success': True,
            'count': len(products),
            'products': products
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM annunci")
        count = cursor.fetchone()[0]
        conn.close()
        
        return jsonify({
            'status': 'ok',
            'database': 'connected',
            'listings': count,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Server error'}), 500

if __name__ == '__main__':
    # Modalità sviluppo
    app.run(debug=True, host='0.0.0.0', port=5000)
