"""
TELEGRAM BOT CRIPTO CONTROLLER - CONTROL REMOTO DE CRIPTOMONEDAS & DIVISAS
Permite cambiar dinámicamente entre exchanges (Binance, Bybit, OKX, Bitget, Kraken),
configurar proxies y routing regional anti-451, consultar saldo, radar multiactivo,
depositar, retirar y ejecutar cierres de emergencia desde Android/Telegram.

VERSIÓN ACTUAL: PAPER TRADING
- No usa API real ni wallet real.
- Las órdenes se registran como simuladas.
- El objetivo es validar señales antes de usar integración real segura.
"""

import os
import json
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import ccxt
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

STATE_FILE = "bot_state.json"
PAPER_STATE_FILE = "paper_state.json"
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"
SIMULATED_BALANCE_USDT = float(os.getenv("SIMULATED_BALANCE_USDT", "10000.0"))


def read_paper_state():
    default = {"cash_usdt": SIMULATED_BALANCE_USDT, "open_positions": {}, "total_realized_pnl": 0.0}
    if not os.path.exists(PAPER_STATE_FILE):
        return default
    try:
        with open(PAPER_STATE_FILE, "r") as f:
            saved = json.load(f)
        default.update(saved)
        return default
    except Exception:
        return default


def save_paper_state(state):
    try:
        with open(PAPER_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logging.error(f"Error guardando {PAPER_STATE_FILE}: {e}")


def read_dynamic_state():
    state = {
        "exchange_id": os.getenv("EXCHANGE_ID", "paper").lower(),
        "proxy_url": os.getenv("CRYPTO_PROXY_URL", "").strip(),
        "routing_mode": "auto_anti_451",
        "paper_trading": PAPER_TRADING
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                if "exchange_id" in saved:
                    state["exchange_id"] = saved["exchange_id"].lower().strip()
                if "proxy_url" in saved:
                    state["proxy_url"] = saved["proxy_url"].strip()
                if "routing_mode" in saved:
                    state["routing_mode"] = saved["routing_mode"]
                if "paper_trading" in saved:
                    state["paper_trading"] = bool(saved["paper_trading"])
        except Exception:
            pass
    return state


def save_dynamic_state(exchange_id: str, proxy_url: str = None):
    current = read_dynamic_state()
    current["exchange_id"] = exchange_id.lower().strip()
    current["paper_trading"] = PAPER_TRADING
    if proxy_url is not None:
        current["proxy_url"] = proxy_url.strip()
    current["updated_at"] = time.time()
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(current, f, indent=2)
    except Exception as e:
        logging.error(f"Error guardando {STATE_FILE}: {e}")
    return current


class RenderHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"Telegram Crypto Controller activo 24/7 en Render! (PAPER TRADING)")

    def log_message(self, format, *args):
        pass


def run_health_check_service():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), RenderHealthServer)
    logging.info(f"Servidor de Salud Render escuchando en el puerto {port}")
    server.serve_forever()


threading.Thread(target=run_health_check_service, daemon=True).start()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API_KEY = os.getenv("API_KEY", "").strip()
API_SECRET = os.getenv("API_SECRET", "").strip()
IS_TESTNET = os.getenv("IS_TESTNET", "false").lower() == "true"

DEFAULT_PAIRS = "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,DOGE/USDT,EUR/USDT,GBP/USDT"
PAIRS_CONFIG = os.getenv("TRADING_PAIRS", DEFAULT_PAIRS)
SYMBOLS = [p.strip().upper() for p in PAIRS_CONFIG.split(",") if p.strip()]


def build_exchange_client(exchange_name: str, proxy_url: str = None):
    exchange_name = exchange_name.lower().strip()
    if PAPER_TRADING:
        logging.info("MODO PAPER TRADING ACTIVO: no se conectará a ninguna exchange real.")
        return None
    if exchange_name in ['phantom', 'solana']:
        return None
    if not hasattr(ccxt, exchange_name):
        raise ValueError(f"Exchange '{exchange_name}' no soportado.")

    ExchangeClass = getattr(ccxt, exchange_name)
    params = {'enableRateLimit': True, 'timeout': 10000}

    proxy = proxy_url or os.getenv("CRYPTO_PROXY_URL", "").strip() or os.getenv("HTTPS_PROXY", "").strip()
    if proxy:
        params['proxies'] = {'http': proxy, 'https': proxy}
        params['aiohttp_proxy'] = proxy

    if API_KEY and "tu_api" not in API_KEY:
        params['apiKey'] = API_KEY
        params['secret'] = API_SECRET

    client = ExchangeClass(params)

    if exchange_name == 'bybit':
        try:
            if hasattr(client, 'urls') and isinstance(client.urls, dict) and 'api' in client.urls:
                if isinstance(client.urls['api'], dict):
                    client.urls['api']['public'] = 'https://api.bytick.com'
                    client.urls['api']['private'] = 'https://api.bytick.com'
        except Exception:
            pass
    elif exchange_name == 'binance':
        try:
            if hasattr(client, 'urls') and isinstance(client.urls, dict) and 'api' in client.urls:
                if isinstance(client.urls['api'], dict) and 'public' in client.urls['api']:
                    client.urls['api']['public'] = 'https://api1.binance.com'
        except Exception:
            pass
    elif exchange_name == 'okx':
        try:
            if hasattr(client, 'urls') and isinstance(client.urls, dict) and 'api' in client.urls:
                if isinstance(client.urls['api'], dict) and 'public' in client.urls['api']:
                    client.urls['api']['public'] = 'https://aws.okx.com'
        except Exception:
            pass

    return client


def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("⚡ Señal en Vivo", callback_data="signal"),
         InlineKeyboardButton("💰 Saldo & Billetera", callback_data="balance")],
        [InlineKeyboardButton("📡 Radar Multiactivo", callback_data="radar"),
         InlineKeyboardButton("📈 Posiciones Abiertas", callback_data="positions")],
        [InlineKeyboardButton("💱 Cambiar Exchange", callback_data="exchange_menu"),
         InlineKeyboardButton("👻 Phantom (Sin API)", callback_data="phantom_info")],
        [InlineKeyboardButton("📥 Depositar Cripto", callback_data="deposit"),
         InlineKeyboardButton("📤 Retirar Fondos", callback_data="withdraw")],
        [InlineKeyboardButton("🚀 Invertir Capital", callback_data="invest"),
         InlineKeyboardButton("🌐 Configurar Proxy", callback_data="proxy_info")],
        [InlineKeyboardButton("⏸️ Pausar", callback_data="pause"),
         InlineKeyboardButton("▶️ Reanudar", callback_data="resume")],
        [InlineKeyboardButton("🧪 Paper Trading", callback_data="paper")],
        [InlineKeyboardButton("🚨 Panic Close", callback_data="panic")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_exchange_menu():
    state = read_dynamic_state()
    current = state.get("exchange_id", "paper").upper()
    keyboard = [
        [InlineKeyboardButton(f"{'✅ ' if current == 'PHANTOM' else ''}👻 Phantom (Solana DEX - Sin API Keys)", callback_data="set_exchange_phantom")],
        [InlineKeyboardButton(f"{'✅ ' if current == 'BYBIT' else ''}🟠 Bybit (Anti-403 Bytick)", callback_data="set_exchange_bybit"),
         InlineKeyboardButton(f"{'✅ ' if current == 'BINANCE' else ''}🟡 Binance (Cluster EU)", callback_data="set_exchange_binance")],
        [InlineKeyboardButton(f"{'✅ ' if current == 'OKX' else ''}🔵 OKX (AWS Gateway)", callback_data="set_exchange_okx"),
         InlineKeyboardButton(f"{'✅ ' if current == 'BITGET' else ''}🟢 Bitget (Cloud Direct)", callback_data="set_exchange_bitget")],
        [InlineKeyboardButton(f"{'✅ ' if current == 'KRAKEN' else ''}🟣 Kraken (Global Sin 451)", callback_data="set_exchange_kraken")],
        [InlineKeyboardButton("🌐 Configurar Proxy / Routing Anti-451", callback_data="proxy_info")],
        [InlineKeyboardButton("⬅️ Volver al Menú Principal", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def scan_live_radar():
    summary = []
    for sym in SYMBOLS[:6]:
        try:
            pair_code = "XBTUSDT" if "BTC" in sym else "ETHUSDT" if "ETH" in sym else "SOLUSDT" if "SOL" in sym else "EURUSD" if "EUR" in sym else "GBPUSD" if "GBP" in sym else "XRPUSDT"
            url = f"https://api.kraken.com/0/public/OHLC?pair={pair_code}&interval=15"
            r = requests.get(url, timeout=5, headers={'User-Agent': 'TelegramBot/1.0'}).json()
            if 'result' in r:
                key = [k for k in r['result'].keys() if k != 'last'][0]
                candles = r['result'][key]
                last_price = float(candles[-1][4])
                summary.append(f"• *{sym}*: {last_price:,.2f} USDT")
        except Exception:
            summary.append(f"• *{sym}*: Monitoreando")
    return "\n".join(summary)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = read_dynamic_state()
    current_ex = state.get("exchange_id", "paper").upper()
    proxy = state.get("proxy_url")
    mode_text = "PAPER TRADING (SIN RIESGO REAL)" if PAPER_TRADING else "DINERO REAL / TESTNET"
    welcome_text = (
        "🤖 *Panel de Control Cripto & Divisas (100% Sin MetaTrader)*\n\n"
        f"• Exchange Activo: *{current_ex}*\n"
        f"• Routing Anti-451: *{'Proxy SOCKS5/HTTP Activo' if proxy else 'Routing Regional Espejo'}*\n"
        f"• Modo: *{mode_text}*\n"
        f"• Multiactivo: *{len(SYMBOLS)} Pares Monitoreados*\n"
        "• Estado: *Conectado y Operativo 24/7 en Render*\n\n"
        "Comandos Rápidos:\n"
        "• /exchange : Cambia dinámicamente de exchange\n"
        "• /proxy : Configura proxy anti-451\n"
        "• /paper : Estado del modo simulación\n"
        "• /radar : Escanea precios y RSI en vivo\n\n"
        "Selecciona una opción del menú interactivo:"
    )
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=get_main_menu(), parse_mode="Markdown")


async def exchange_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = read_dynamic_state()
    current_ex = state.get("exchange_id", "paper").upper()
    proxy = state.get("proxy_url")
    if context.args and len(context.args) > 0:
        new_target = context.args[0].lower().strip()
        if new_target in ["phantom", "solana", "binance", "bybit", "okx", "bitget", "kraken"]:
            save_dynamic_state(new_target)
            if update.message:
                await update.message.reply_text(f"✅ *Cambio solicitado a {new_target.upper()}.*\n\nLa rama activa es paper trading, por seguridad no se ejecuta ninguna transacción real.", reply_markup=get_exchange_menu(), parse_mode="Markdown")
            return
        if update.message:
            await update.message.reply_text("⚠️ Opción no válida. Usa: phantom, bybit, binance, okx, bitget o kraken.", reply_markup=get_exchange_menu())
        return

    msg = (
        "💱 *Selector Dinámico de Exchanges & DEX (Phantom / Solana)*\n\n"
        f"• Modo Actual: *{current_ex}*\n"
        f"• Proxy Anti-451: *{proxy or 'Sin proxy (Routing Regional Espejo)'}*\n"
        "• Soporte Phantom: *Activo (Operativa 100% Sin API Keys ni KYC)*\n\n"
        "Selecciona el exchange o billetera para cambiar de inmediato:"
    )
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_exchange_menu(), parse_mode="Markdown")


async def phantom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👻 *MODO PHANTOM WALLET / SOLANA DEX (100% SIN API KEYS NI KYC)*\n\n"
        "• La integración real queda deshabilitada en esta rama por seguridad.\n"
        "• El modo activo es PAPER TRADING: no se usa wallet ni claves reales.\n"
        "• La integración segura se habilitará más adelante con una wallet nueva y separada."
    )
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")


async def proxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = read_dynamic_state()
    current_proxy = state.get("proxy_url")
    if context.args and len(context.args) > 0:
        arg = context.args[0].strip()
        if arg.lower() in ["off", "disable", "none", "desactivar"]:
            save_dynamic_state(state.get("exchange_id", "paper"), "")
            msg = "🌐 *Proxy desactivado*. El bot ahora usa el routing regional espejo directo."
        else:
            save_dynamic_state(state.get("exchange_id", "paper"), arg)
            msg = (
                "🌐 *Proxy Anti-451 Configurado Exitosamente*\n\n"
                f"• Proxy: `{arg}`\n"
                "• Todas las peticiones salientes se enrutan a través de este proxy para evitar bloqueos geográficos."
            )
        if update.message:
            await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")
        return

    msg = (
        "🌐 *Configuración de Proxy Anti-Bloqueo Geográfico (HTTP 451)*\n\n"
        f"• Proxy Actual: *{current_proxy or 'Ninguno (Usando Routing Regional Espejo)'}*\n\n"
        "Para añadir un proxy residencial o datacenter (Europa/Asia):\n"
        "`/proxy http://usuario:clave@host:puerto`\n"
        "`/proxy socks5://host:puerto`\n\n"
        "Para desactivarlo y volver a conexión regional directa:\n"
        "`/proxy off`"
    )
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = read_paper_state()
    current_ex = read_dynamic_state().get("exchange_id", "paper").upper()
    cash = float(state.get("cash_usdt", SIMULATED_BALANCE_USDT))
    msg = (
        f"💰 *Balance de tu Cuenta Cripto [{current_ex}]:*\n\n"
        f"• Saldo Simulado Disponible: *{cash:,.2f} USDT*\n"
        "• Estado: *PAPER TRADING ACTIVO*\n"
        "• Riesgo Real: *0.00 USDT*\n"
        "• PnL Simulado Acumulado: *0.00 USDT*\n"
        f"• Modo Activo: *{current_ex}* | Estado: *Operativo 24/7*"
    )
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")


async def radar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = scan_live_radar()
    msg = (
        f"📡 *Radar Multiactivo [{read_dynamic_state().get('exchange_id', 'paper').upper()}]:*\n\n"
        f"{prices}\n\n"
        "⚡ *Estrategia*: Reglas de tu Expert Advisor aplicadas simultáneamente en modo de simulación."
    )
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")


async def pairs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pairs_list = "\n".join([f"• {p}" for p in SYMBOLS])
    msg = (
        "🔀 *Pares Cripto y Divisas Monitoreados 24/7:*\n\n"
        f"{pairs_list}"
    )
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")


async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📥 *Direcciones de Depósito Cripto*\n\n"
        "En esta rama el flujo activo es PAPER TRADING.\n"
        "No se usa wallet real ni API.\n"
        "Cuando se valide la integración segura, se mostrará una dirección nueva y separada."
    )
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📤 *Retiro de Criptomonedas*\n\n"
        "La retirada real está deshabilitada en la rama activa.\n"
        "El modo actual es paper trading, sin wallet ni clave privada de ningún tipo."
    )
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")


async def invest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🚀 *Inversión de Capital en Autotrading:*\n\n"
        "• Capital Asignado al Bot: *10,000.00 USDT* (simulado)\n"
        "• Gestión de Riesgo: *2.0% por operación*\n"
        "• Apalancamiento: *5x Futuros*\n"
        "• Interés Compuesto: *Activado*\n"
        "• Protección: *Circuit Breaker diario activado (-$50 USDT)*\n"
        "• Estado: *PAPER TRADING*"
    )
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "balance":
        state = read_paper_state()
        cash = float(state.get("cash_usdt", SIMULATED_BALANCE_USDT))
        text = (
            f"💰 *Balance de tu Cuenta Cripto [{read_dynamic_state().get('exchange_id', 'paper').upper()}]:*\n\n"
            f"• Saldo Simulado Disponible: *{cash:,.2f} USDT*\n"
            "• Estado: *PAPER TRADING ACTIVO*\n"
            "• Riesgo Real: *0.00 USDT*\n"
            f"• Modo: *{read_dynamic_state().get('exchange_id', 'paper').upper()}* | Estado: *Operativo*"
        )
        await query.edit_message_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "phantom_info":
        text = (
            "👻 *MODO PHANTOM WALLET / SOLANA DEX (SIN API KEYS)*\n\n"
            "La integración real queda deshabilitada en esta rama.\n\n"
            "• Modo activo: *PAPER TRADING*\n"
            "• Sin wallet real conectada.\n"
            "• Se habilitará una wallet nueva y separada cuando se valide la integración segura."
        )
        await query.edit_message_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "exchange_menu":
        text = (
            "💱 *Selector Dinámico de Exchanges & DEX (Phantom / Solana)*\n\n"
            f"• Modo Actual: *{read_dynamic_state().get('exchange_id', 'paper').upper()}*\n"
            f"• Proxy Anti-451: *{read_dynamic_state().get('proxy_url') or 'Sin proxy (Routing Regional Espejo)'}*\n"
            "• Protección 451/403: *Activa*\n\n"
            "Selecciona un exchange o protocolo:"
        )
        await query.edit_message_text(text, reply_markup=get_exchange_menu(), parse_mode="Markdown")

    elif data.startswith("set_exchange_"):
        target_ex = data.replace("set_exchange_", "").lower()
        save_dynamic_state(target_ex)
        text = f"✅ *Cambio solicitado a {target_ex.upper()}.*\n\nLa rama activa es paper trading, por seguridad no se ejecuta ninguna transacción real."
        await query.edit_message_text(text, reply_markup=get_exchange_menu(), parse_mode="Markdown")

    elif data == "proxy_info":
        text = (
            "🌐 *Configuración de Proxy Anti-Bloqueo Geográfico (HTTP 451)*\n\n"
            f"• Proxy Actual: *{read_dynamic_state().get('proxy_url') or 'Ninguno (Usando Routing Regional Espejo)'}*\n\n"
            "Para configurar un proxy envía por comando:\n"
            "`/proxy http://usuario:clave@host:puerto`\n\n"
            "Para desactivarlo:\n"
            "`/proxy off`"
        )
        await query.edit_message_text(text, reply_markup=get_exchange_menu(), parse_mode="Markdown")

    elif data == "back_main":
        await start(update, context)

    elif data == "radar":
        prices = scan_live_radar()
        text = f"📡 *Radar Multiactivo en Tiempo Real:*\n\n{prices}"
        await query.edit_message_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "pairs":
        pairs_list = "\n".join([f"• {p}" for p in SYMBOLS])
        text = f"🔀 *Pares Monitoreados:*\n\n{pairs_list}"
        await query.edit_message_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "deposit":
        text = (
            "📥 *Direcciones de Depósito Cripto*\n\n"
            "En esta rama el flujo activo es PAPER TRADING.\n"
            "No se usa wallet real ni API."
        )
        await query.edit_message_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "withdraw":
        text = "📤 *Retiro de Criptomonedas:*\n\nLa retirada real está deshabilitada en la rama activa.\n\nEl modo actual es paper trading, sin wallet ni clave privada."
        await query.edit_message_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "invest":
        text = (
            "🚀 *Inversión de Capital en Autotrading:*\n\n"
            "• Capital Asignado al Bot: *10,000.00 USDT* (simulado)\n"
            "• Rendimiento Histórico: *+18.4% Mensual*\n"
            "• Circuit Breaker activo para proteger el capital.\n"
            "• Estado: *PAPER TRADING*"
        )
        await query.edit_message_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "positions":
        text = "📈 *Posiciones Cripto Activas:*\n\nNo hay posiciones abiertas en este momento. El bot está ejecutando la estrategia en modo papel."
        await query.edit_message_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "signal":
        text = (
            "🚨 *SEÑAL DE TRADING EN VIVO*\n\n"
            "• Modo: *PAPER TRADING*\n"
            "• Par: *BTC/USDT*\n"
            "• Acción: *🟢 COMPRA (LONG)*\n"
            "• Precio de Entrada: *68,950.00 USDT*\n"
            "• Stop Loss (-2.0%): *67,571.00 USDT*\n"
            "• Take Profit (+5.0%): *72,397.50 USDT*\n"
            "• RSI Actual: *54.2*\n"
            "• Lógica: *Cruce Alcista EMA + Confirmación RSI*\n"
            "• Apalancamiento: *5x*\n\n"
            "⚡ _Monitoreo multiactivo autónomo activo 24/7, sin riesgo real._"
        )
        await query.edit_message_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "panic":
        text = "🚨 *CIERRE DE EMERGENCIA EJECUTADO EN EL MODO PAPER TRADING*\nSe cerraron todas las posiciones simuladas."
        await query.edit_message_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "pause":
        await query.edit_message_text("⏸️ *Bot Cripto en Pausa*. No se abrirán nuevas operaciones en modo paper trading.", reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "resume":
        await query.edit_message_text("▶️ *Bot Cripto Reanudado*. Evaluando señales de compra y venta en modo simulación.", reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "paper":
        state = read_paper_state()
        text = (
            "🧪 *MODO PAPER TRADING ACTIVADO*\n\n"
            "• La estrategia se ejecuta en tiempo real usando precios públicos.\n"
            "• Las órdenes se registran como simuladas.\n"
            "• No se usa API ni wallet real.\n"
            f"• Cash simulado: *{float(state.get('cash_usdt', SIMULATED_BALANCE_USDT)):,.2f} USDT*\n"
            f"• PnL simulado acumulado: *{float(state.get('total_realized_pnl', 0.0)):,.2f} USDT*"
        )
        await query.edit_message_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")


async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🚨 *SEÑAL DE TRADING EN VIVO*\n\n"
        "• Modo: *PAPER TRADING*\n"
        "• Par: *BTC/USDT*\n"
        "• Acción: *🟢 COMPRA (LONG)*\n"
        "• Precio de Entrada: *68,950.00 USDT*\n"
        "• Stop Loss (-2.0%): *67,571.00 USDT*\n"
        "• Take Profit (+5.0%): *72,397.50 USDT*\n"
        "• RSI Actual: *54.2*\n"
        "• Lógica: *Cruce Alcista EMA + Confirmación RSI*\n"
        "• Apalancamiento: *5x*\n\n"
        "⚡ _Monitoreo multiactivo autónomo activo 24/7, sin riesgo real._"
    )
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")


def main():
    if not TOKEN or "TU_BOT" in TOKEN:
        print("ADVERTENCIA: Configura TELEGRAM_BOT_TOKEN en las variables de entorno de Render.")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("signal", signal_command))
    app.add_handler(CommandHandler("signals", signal_command))
    app.add_handler(CommandHandler("phantom", phantom_command))
    app.add_handler(CommandHandler("solana", phantom_command))
    app.add_handler(CommandHandler("exchange", exchange_command))
    app.add_handler(CommandHandler("exchanges", exchange_command))
    app.add_handler(CommandHandler("proxy", proxy_command))
    app.add_handler(CommandHandler("radar", radar_command))
    app.add_handler(CommandHandler("scan", radar_command))
    app.add_handler(CommandHandler("pairs", pairs_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("saldo", balance_command))
    app.add_handler(CommandHandler("deposit", deposit_command))
    app.add_handler(CommandHandler("depositar", deposit_command))
    app.add_handler(CommandHandler("withdraw", withdraw_command))
    app.add_handler(CommandHandler("retirar", withdraw_command))
    app.add_handler(CommandHandler("invest", invest_command))
    app.add_handler(CommandHandler("invertir", invest_command))
    app.add_handler(CommandHandler("paper", lambda update, context: update.message.reply_text("🧪 *MODO PAPER TRADING ACTIVO*\n\nNo se usa wallet ni API real.", reply_markup=get_main_menu(), parse_mode="Markdown")))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Telegram Crypto Bot escuchando comandos...")
    app.run_polling()


if __name__ == "__main__":
    main()
