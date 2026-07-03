"""
Entry point del bot Telegram interattivo (evoluzione richiesta rispetto al
semplice invio di notifiche).

Questo e un PROCESSO SEPARATO rispetto a main.py: main.py continua a
occuparsi della ricerca automatica in background e delle notifiche per gli
"affari eccellenti" (vedi main.py e ranking.py); questo script gestisce
invece le interazioni dirette con l'utente (ricerche libere, menu, bottoni).

I due processi condividono lo stesso database SQLite, quindi possono girare
insieme senza conflitti: main.py popola il database con nuovi annunci,
questo bot legge/scrive nello stesso database per servire le richieste
dell'utente in tempo reale.

Esecuzione:
    python3 telegram_interactive_bot.py

Richiede TELEGRAM_BOT_TOKEN configurato in .env (lo stesso token gia usato
da telegram_bot.py per le notifiche automatiche - e lo stesso bot, solo con
due modalita di interazione: notifiche push da main.py, comandi/chat da qui).
"""

import logging

from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

import config
import database
import telegram_handlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def costruisci_applicazione() -> Application:
    """Costruisce e configura l'Application di python-telegram-bot con tutti gli handler."""
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN non configurato in .env. "
            "Il bot interattivo non puo avviarsi senza un token valido."
        )

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Comandi (punto 13 della richiesta)
    app.add_handler(CommandHandler("start", telegram_handlers.cmd_start))
    app.add_handler(CommandHandler("help", telegram_handlers.cmd_help))
    app.add_handler(CommandHandler("search", telegram_handlers.cmd_search))
    app.add_handler(CommandHandler("history", telegram_handlers.cmd_history))
    app.add_handler(CommandHandler("favorites", telegram_handlers.cmd_favorites))
    app.add_handler(CommandHandler("stats", telegram_handlers.cmd_stats))
    app.add_handler(CommandHandler("dashboard", telegram_handlers.cmd_dashboard))
    app.add_handler(CommandHandler("settings", telegram_handlers.cmd_settings))

    # Click sui bottoni inline (punto 3)
    app.add_handler(CallbackQueryHandler(telegram_handlers.gestisci_callback))

    # Qualsiasi testo che non sia un comando -> ricerca libera (punto 4).
    # Va registrato DOPO i CommandHandler, cosi i comandi vengono
    # intercettati prima e non finiscono qui per errore.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_handlers.gestisci_testo_libero))

    # Error handler globale (punto 18: robustezza)
    app.add_error_handler(telegram_handlers.gestisci_errori_globali)

    return app


def main() -> None:
    database.init_db()  # assicura che tutte le tabelle (incluse quelle nuove) esistano

    logger.info("Avvio del bot Telegram interattivo di Vinted Hunter...")
    app = costruisci_applicazione()

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
