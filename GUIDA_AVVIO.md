# 🚀 Guida Completa - PriceRadar v2.0

**Sistema completo zero crash per il reselling quotidiano**

---

## 📋 Indice
1. [Setup Iniziale](#setup-iniziale)
2. [Configurazione](#configurazione)
3. [Avvio del Sistema](#avvio-del-sistema)
4. [Dashboard Web](#dashboard-web)
5. [Bot Telegram](#bot-telegram)
6. [Troubleshooting](#troubleshooting)
7. [Comandi Utili](#comandi-utili)

---

## Setup Iniziale

### 1️⃣ Prerequisiti

```bash
# Python 3.9+
python3 --version

# Pip aggiornato
pip install --upgrade pip
```

### 2️⃣ Clone Repository

```bash
cd ~/projects  # o dove preferisci
git clone https://github.com/zerozilliotto-hash/PriceRadar.git
cd PriceRadar
```

### 3️⃣ Ambiente Virtuale

```bash
# Crea ambiente isolato
python3 -m venv venv

# Attiva
source venv/bin/activate        # Linux/Mac
# oppure
venv\Scripts\activate           # Windows
```

### 4️⃣ Installa Dipendenze

```bash
pip install -r requirements.txt

# Se requirements.txt non è aggiornato, installa manualmente:
pip install python-telegram-bot flask flask-cors sqlite3 \
    anthropic requests beautifulsoup4 lxml pillow pytesseract \
    scikit-learn pandas numpy
```

---

## Configurazione

### 1️⃣ Copia template .env

```bash
cp .env.example .env
```

### 2️⃣ Compila .env con i tuoi dati

```bash
# Apri con editor preferito
nano .env
# oppure
code .env
```

#### Credenziali Necessarie:

```env
# TELEGRAM (OBBLIGATORIO)
TELEGRAM_TOKEN=123456:ABCDEFGHIJKLMNOP
TELEGRAM_CHAT_IDS=123456789,987654321

# ANTHROPIC API (per riconoscimento prodotto/traduzione)
ANTHROPIC_API_KEY=sk-ant-xxxxxx

# MARKETPLACE CREDENTIALS
EBAY_TOKEN=xxxxxxx                    # opzionale
DEPOP_AUTH_TOKEN=xxxxx               # opzionale

# CONFIGURAZIONE SISTEMA
ABILITA_RICONOSCIMENTO_PRODOTTO=True
ABILITA_TRADUZIONE_AUTOMATICA=True
ABILITA_STIMA_PROFITTO=True
MARGINE_COSTI_PERCENTO=12.0
```

### 3️⃣ Come ottenere le credenziali

#### 🤖 Telegram Bot Token
```
1. Apri Telegram e cerca @BotFather
2. Scrivi /newbot
3. Segui i passaggi
4. Copia il token (esempio: 123456:ABCxyz...)
```

#### 🆔 Telegram Chat IDs
```
1. Apri questo bot: @userinfobot
2. Scrivi qualcosa
3. Lui ti dice il tuo ID
4. Separali con virgola: 123456789,987654321
```

#### 🔑 Anthropic API Key
```
1. Vai su https://console.anthropic.com
2. Accedi con account Google/GitHub
3. Crea una nuova API key
4. Copia in .env
```

---

## Avvio del Sistema

### 📊 Opzione 1: Avvio Manuale (sviluppo/test)

**Terminal 1: Loop ricerca automatico**
```bash
python3 main.py --loop
```

**Terminal 2: Bot Telegram**
```bash
python3 telegram_bot_robust.py
```

**Terminal 3: Dashboard web**
```bash
cd webapp && python3 app.py
```

Accedi a:
- 🌐 **Dashboard**: http://localhost:5000
- 💬 **Bot**: Cerca su Telegram lo username del tuo bot

### 🐋 Opzione 2: Docker (produzione)

```bash
# Crea docker-compose.yml nella root
docker-compose up -d

# Logs
docker-compose logs -f
```

### 🖥️ Opzione 3: Systemd (Linux - produzione)

```bash
sudo systemctl enable priceradar
sudo systemctl start priceradar
sudo systemctl status priceradar
```

---

## Dashboard Web

### 📊 Accesso

```
🌐 http://localhost:5000
```

### ✨ Funzionalità

#### 🔍 Filtri Avanzati
- **Marketplace**: Vinted, eBay, Depop, Subito
- **Range Prezzo**: Min/Max
- **ROI Minimo**: Filtra per profittabilità
- **Marca**: Ricerca brand
- **Colore**: Filtro per colore principale

#### 📊 Visualizzazione Prodotti
Ogni card mostra:
- 📸 **Foto principale**
- 🎯 **Titolo e marketplace**
- 💵 **Prezzo annuncio vs. valore mercato**
- 💎 **Profitto stimato e ROI**
- 📊 **Barra ROI visuale**
- ⭐ **Score venditore**

#### 📈 Grafici
- **Distribuzione Prezzi** (bar chart)
- **ROI vs Prezzo** (scatter plot)

---

## Bot Telegram

### 💬 Comandi Disponibili

```
/start      - Menu principale
/search     - Ricerca prodotto
/trending   - Migliori affari ultimi 24h
/stats      - Statistiche globali
/help       - Aiuto e comandi
```

### 🔍 Esempi Ricerca

Il bot accetta query naturali:
```
"Nike Jordan 4 sotto 150 euro"
"Adidas grigia 42"
"Sony PS5 da 200 a 400"
"Scarpe nere taglia 42"
```

### ✨ Features Bot

✅ **Ricerca intelligente** - riconosce marca, prezzo, colore
✅ **Rate limiting** - 30 richieste/minuto per utente
✅ **Cache** - evita ricerche duplicate
✅ **Foto** - mostra immagine prodotto
✅ **Info ROI** - calcolo profitto in real-time
✅ **Bottoni rapidi** - Apri, Preferito, Visto
✅ **Zero crash** - gestione errori completa
✅ **Timeout protezione** - riconnessione automatica

---

## Troubleshooting

### ❌ Errore: "Database Locked"

```bash
# Soluzione: usa un solo processo per volta
# O abilita WAL mode nel config
```

### ❌ Errore: "Telegram Token Non Valido"

```bash
# Verifica token in .env
# Controlla che sia completo: 123456:ABCxyz...
```

### ❌ Dashboard mostra 0 annunci

```bash
# Verifica se DB ha dati:
sqlite3 annunci.db "SELECT COUNT(*) FROM annunci;"

# Se 0: avvia main.py --loop per raccogliere dati
```

### ❌ Bot non risponde

```bash
# Riavvia bot
pkill -f telegram_bot_robust.py
python3 telegram_bot_robust.py

# Verifica logs
tail -f priceradar.log
```

---

## 🎯 Checklist Setup Completato

- [ ] Python 3.9+ installato
- [ ] Repository clonato
- [ ] Ambiente virtuale attivo
- [ ] Dipendenze installate
- [ ] `.env` configurato con credenziali
- [ ] Bot Telegram creato con @BotFather
- [ ] Test eseguiti: `python3 -m pytest tests/ -q`
- [ ] Main.py avviato (raccoglie dati)
- [ ] Bot Telegram avviato
- [ ] Dashboard web accessibile
- [ ] Database ha almeno 10 annunci
- [ ] Ricerca su Telegram funziona

---

## 🎉 Pronto!

Hai tutto quello che serve per:
- ✅ Ricerca marketplace automatica
- ✅ Dashboard bella e intuitiva
- ✅ Bot Telegram sempre disponibile
- ✅ Calcolo profitto/ROI automatico
- ✅ Zero crash, errori gestiti

**Buon reselling! 🚀**
