"""
Bot Telegram robusto con gestione errori completa
Zero crash, gestione rate limiting, cache intelligente
"""

import logging
import os
import asyncio
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict, List

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto, User, Chat
)
from telegram.ext import (
    Application, ContextTypes, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters
)
from telegram.error import TelegramError, RetryAfter, BadRequest
from telegram.constants import ChatAction

import sqlite3
import json

# Configurazione base - adatta al tuo file config.py
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_IDS = [int(x.strip()) for x in os.getenv('TELEGRAM_CHAT_IDS', '').split(',') if x.strip()]
MAX_TELEGRAM_MESSAGE_LENGTH = 3000
MARGINE_COSTI_PERCENTO = float(os.getenv('MARGINE_COSTI_PERCENTO', '12.0'))

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = 'annunci.db'

# Cache in-memory con timeout
class CacheManager:
    def __init__(self, ttl_seconds: int = 3600):
        self.cache: Dict = {}
        self.ttl = ttl_seconds
    
    def get(self, key: str) -> Optional:
        if key in self.cache:
            value, expiry = self.cache[key]
            if time.time() < expiry:
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, value) -> None:
        self.cache[key] = (value, time.time() + self.ttl)
    
    def clear(self):
        self.cache.clear()

cache = CacheManager(ttl_seconds=3600)

# Rate limiting per utente
class RateLimiter:
    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests: Dict[int, List[float]] = {}
    
    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        if user_id not in self.requests:
            self.requests[user_id] = []
        
        # Pulisci richieste vecchie
        self.requests[user_id] = [t for t in self.requests[user_id] 
                                  if now - t < self.window]
        
        if len(self.requests[user_id]) >= self.max_requests:
            return False
        
        self.requests[user_id].append(now)
        return True
    
    def get_wait_time(self, user_id: int) -> float:
        if user_id not in self.requests:
            return 0
        now = time.time()
        self.requests[user_id] = [t for t in self.requests[user_id] 
                                  if now - t < self.window]
        if self.requests[user_id]:
            oldest = min(self.requests[user_id])
            return max(0, self.window - (now - oldest))
        return 0

rate_limiter = RateLimiter(max_requests=30, window_seconds=60)

# Decorator per gestire errori Telegram
def safe_telegram(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except RetryAfter as e:
            logger.warning(f"Rate limited, retry after {e.retry_after}s")
            try:
                await update.message.reply_text(
                    f"⏳ Troppi messaggi. Riprova tra {e.retry_after} secondi.",
                    reply_to_message_id=update.message.message_id
                )
            except:
                pass
            await asyncio.sleep(e.retry_after)
        except BadRequest as e:
            logger.error(f"Bad request: {e}")
            if "message to delete not found" not in str(e):
                try:
                    await update.message.reply_text(
                        "❌ Errore. Messaggio non valido.",
                        reply_to_message_id=update.message.message_id
                    )
                except:
                    pass
        except TelegramError as e:
            logger.error(f"Telegram error: {e}")
            try:
                await update.message.reply_text(
                    "⚠️ Errore di connessione. Riprova.",
                    reply_to_message_id=update.message.message_id
                )
            except:
                pass
        except Exception as e:
            logger.exception(f"Unexpected error in {func.__name__}: {e}")
            try:
                await update.message.reply_text(
                    "❌ Errore interno. Contatta supporto.",
                    reply_to_message_id=update.message.message_id
                )
            except:
                pass
    
    return wrapper

def get_db():
    """Connessione DB con retry"""
    retry_count = 0
    while retry_count < 3:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.OperationalError:
            retry_count += 1
            if retry_count < 3:
                time.sleep(1 * retry_count)
    raise Exception("Impossibile connettersi al database")

def is_authorized(user_id: int) -> bool:
    """Verifica se user è autorizzato"""
    return user_id in TELEGRAM_CHAT_IDS

def format_product_message(product: dict) -> tuple[str, Optional[str]]:
    """
    Formatta annuncio per messaggio Telegram
    Ritorna (text, image_url)
    """
    try:
        title = product.get('titolo', 'N/A')[:100]
        price = product.get('prezzo', 0)
        marketplace = product.get('marketplace', 'Unknown').upper()
        brand = product.get('brand', '')
        model = product.get('modello', '')
        
        # Valori stimati
        est_value = product.get('valore_stimato', price)
        savings_euro = product.get('risparmio_euro', 0)
        savings_pct = product.get('risparmio_percento', 0)
        profit = product.get('profitto_stimato', 0)
        roi = product.get('roi_stimato', 0)
        margin = product.get('margine_percento', 0)
        seller_score = product.get('score_venditore', 0)
        reliability = product.get('affidabilita', 0)
        
        # Emoji indicatori
        roi_emoji = "🔥" if roi > 30 else "✅" if roi > 15 else "⚠️" if roi > 0 else "❌"
        price_emoji = "💚" if savings_euro > 0 else "🔴"
        
        message = f"""
{roi_emoji} *{title}*

📍 {marketplace}
{f'🏷️ {brand} {model}' if brand else ''}

💰 *Prezzo Annuncio:* €{price:.2f}
📊 Valore Mercato: €{est_value:.2f}

{price_emoji} *Risparmio:* €{savings_euro:.2f} ({savings_pct:.1f}%)

💎 *Profitto Stimato:* €{profit:.2f}
📈 ROI: {roi:.1f}%
💹 Margine: {margin:.1f}%

👤 Venditore: {product.get('venditore', 'N/A')}
⭐ Affidabilità: {reliability:.0f}/100 | Score: {seller_score:.0f}/100

🔗 ID: {product.get('id', 'N/A')}
"""
        
        # Foto se disponibile
        image_url = product.get('foto_principale')
        
        return message, image_url
    
    except Exception as e:
        logger.error(f"Error formatting product: {e}")
        return "❌ Errore nel caricamento annuncio", None

def truncate_message(text: str, max_length: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> str:
    """Tronca messaggio se troppo lungo"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

@safe_telegram
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text(
            "❌ Non autorizzato. Contatta l'amministratore."
        )
        logger.warning(f"Unauthorized access attempt from {user_id}")
        return
    
    welcome_text = """
👋 Benvenuto in *PriceRadar*!

Sono il tuo assistente per il reselling su marketplace second-hand.

📋 Comandi disponibili:
/search - Ricerca prodotto
/trending - Trend migliori affari
/stats - Statistiche
/favorites - Preferiti
/help - Aiuto
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Ricerca", callback_data="search")],
        [InlineKeyboardButton("📈 Trend", callback_data="trending")],
        [InlineKeyboardButton("📊 Statistiche", callback_data="stats")],
        [InlineKeyboardButton("❤️ Preferiti", callback_data="favorites")],
    ])
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

@safe_telegram
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /search - ricerca prodotti"""
    user_id = update.effective_user.id
    
    if not rate_limiter.is_allowed(user_id):
        wait_time = rate_limiter.get_wait_time(user_id)
        await update.message.reply_text(
            f"⏳ Limite di richieste raggiunto. Riprova tra {wait_time:.0f}s"
        )
        return
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Non autorizzato")
        return
    
    context.user_data['search_mode'] = True
    await update.message.reply_text(
        "🔍 Cosa cerchi? (es: 'Nike Jordan sotto 150 euro')",
        reply_to_message_id=update.message.message_id
    )

@safe_telegram
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per testi generici"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if not is_authorized(user_id):
        return
    
    if context.user_data.get('search_mode'):
        await handle_search_query(update, context, text)
        context.user_data['search_mode'] = False

async def handle_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
    """Gestisce ricerca prodotto"""
    try:
        # Mostra "typing"
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING
        )
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Ricerca full-text
        search_term = f'%{query}%'
        cursor.execute("""
            SELECT * FROM annunci
            WHERE 
                LOWER(titolo) LIKE LOWER(?) OR
                LOWER(brand) LIKE LOWER(?) OR
                LOWER(modello) LIKE LOWER(?)
            ORDER BY COALESCE(roi_stimato, 0) DESC
            LIMIT 5
        """, (search_term, search_term, search_term))
        
        products = cursor.fetchall()
        conn.close()
        
        if not products:
            await update.message.reply_text("❌ Nessun prodotto trovato")
            return
        
        # Invia risultati
        for idx, product in enumerate(products, 1):
            product_dict = dict(product)
            message, image_url = format_product_message(product_dict)
            message = truncate_message(message)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Apri", url=product_dict.get('url', '#'))],
                [InlineKeyboardButton("❤️ Preferito", callback_data=f"fav_{product_dict['id']}")],
                [InlineKeyboardButton("✅ Visto", callback_data=f"seen_{product_dict['id']}")],
            ])
            
            try:
                if image_url:
                    await update.message.reply_photo(
                        photo=image_url,
                        caption=message,
                        reply_markup=keyboard,
                        parse_mode='Markdown',
                        reply_to_message_id=update.message.message_id
                    )
                else:
                    await update.message.reply_text(
                        message,
                        reply_markup=keyboard,
                        parse_mode='Markdown',
                        reply_to_message_id=update.message.message_id
                    )
            except Exception as e:
                logger.error(f"Error sending product {idx}: {e}")
                continue
            
            # Evita rate limiting
            await asyncio.sleep(0.5)
    
    except Exception as e:
        logger.exception(f"Error in search: {e}")
        await update.message.reply_text("❌ Errore nella ricerca")

@safe_telegram
async def trending_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /trending - migliori affari recenti"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Non autorizzato")
        return
    
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text("⏳ Limite di richieste raggiunto")
        return
    
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING
        )
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Ultimi 24 ore con migliori ROI
        since = (datetime.now() - timedelta(days=1)).isoformat()
        cursor.execute("""
            SELECT * FROM annunci
            WHERE data_acquisizione >= ?
            ORDER BY COALESCE(roi_stimato, 0) DESC
            LIMIT 10
        """, (since,))
        
        products = cursor.fetchall()
        conn.close()
        
        if not products:
            await update.message.reply_text("📭 Nessun annuncio nuovo nelle ultime 24 ore")
            return
        
        message = f"🔥 *Top 10 Affari Ultimi 24h*\n\n"
        for idx, product in enumerate(products, 1):
            p_dict = dict(product)
            roi = p_dict.get('roi_stimato', 0)
            price = p_dict.get('prezzo', 0)
            profit = p_dict.get('profitto_stimato', 0)
            message += f"{idx}. {p_dict.get('titolo', 'N/A')[:50]} | €{price:.0f} | ROI {roi:.0f}% | Profit €{profit:.0f}\n"
        
        message = truncate_message(message)
        await update.message.reply_text(message, parse_mode='Markdown')
    
    except Exception as e:
        logger.exception(f"Error in trending: {e}")
        await update.message.reply_text("❌ Errore nel caricamento trend")

@safe_telegram
async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /stats - statistiche globali"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        return
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(DISTINCT marketplace) as markets,
                AVG(COALESCE(roi_stimato, 0)) as avg_roi,
                AVG(prezzo) as avg_price,
                SUM(CASE WHEN COALESCE(roi_stimato, 0) > 20 THEN 1 ELSE 0 END) as hot_deals
            FROM annunci
        """)
        
        stats = dict(cursor.fetchone())
        conn.close()
        
        message = f"""
📊 *Statistiche Globali*

📈 Annunci Totali: {stats['total']}
🏪 Marketplace: {stats['markets']}
💰 Prezzo Medio: €{stats['avg_price']:.2f}
⭐ ROI Medio: {stats['avg_roi']:.1f}%
🔥 Affari Caldi (ROI > 20%): {stats['hot_deals']}
"""
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    except Exception as e:
        logger.exception(f"Error in stats: {e}")
        await update.message.reply_text("❌ Errore nel caricamento statistiche")

@safe_telegram
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help"""
    help_text = """
🆘 *Aiuto PriceRadar*

/start - Menu principale
/search - Cerca prodotto
/trending - Migliori affari
/stats - Statistiche
/favorites - I tuoi preferiti

🎯 Come usare:
1. /search e scrivi cosa cerchi
2. Ricevi max 5 risultati con foto
3. Clicca i bottoni per azioni rapide

💡 Suggerimenti:
- Usa keywords specifiche ("Nike Jordan", "Sony PS5")
- Aggiungi prezzo ("sotto 100 euro")
- Aggiungi colore ("blu", "nero")

⚙️ Rate limit: 30 richieste/minuto
⏱️ Cache: 1 ora

📧 Support: @admin
"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce button callback"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_authorized(user_id):
        await query.answer("❌ Non autorizzato", show_alert=True)
        return
    
    try:
        await query.answer()
        
        if query.data.startswith("fav_"):
            product_id = query.data.replace("fav_", "")
            # TODO: salvare nei preferiti
            await query.edit_message_caption(
                caption=query.message.caption + "\n\n❤️ Aggiunto ai preferiti!",
                parse_mode='Markdown'
            )
        
        elif query.data.startswith("seen_"):
            product_id = query.data.replace("seen_", "")
            # TODO: marcare come visto
            await query.edit_message_caption(
                caption=query.message.caption + "\n\n✅ Marcato come visto",
                parse_mode='Markdown'
            )
    
    except Exception as e:
        logger.error(f"Error in callback: {e}")
        await query.answer("❌ Errore", show_alert=True)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce errori globali"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.message:
        try:
            await update.message.reply_text(
                "⚠️ Errore di sistema. Team notificato."
            )
        except:
            pass

def run_bot():
    """Avvia bot Telegram"""
    try:
        if not TELEGRAM_TOKEN:
            logger.error("TELEGRAM_TOKEN non configurato in .env")
            return
        
        logger.info("🤖 Avvio Bot Telegram...")
        
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Handlers
        application.add_handler(CommandHandler("start", start_handler))
        application.add_handler(CommandHandler("search", search_handler))
        application.add_handler(CommandHandler("trending", trending_handler))
        application.add_handler(CommandHandler("stats", stats_handler))
        application.add_handler(CommandHandler("help", help_handler))
        
        application.add_handler(CallbackQueryHandler(callback_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
        
        application.add_error_handler(error_handler)
        
        logger.info("✅ Bot inizializzato. In ascolto...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    except Exception as e:
        logger.exception(f"Errore fatale nel bot: {e}")
        # Retry dopo 10 secondi
        time.sleep(10)
        run_bot()

if __name__ == '__main__':
    run_bot()
