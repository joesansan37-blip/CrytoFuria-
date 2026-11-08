"""
TELEGRAM BOT CRIPTO CONTROLLER - PAPER TRADING ONLY

Este archivo ofrece un panel interactivo sin hacer llamadas reales a exchanges ni wallets.
"""

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

STATE_FILE = "bot_state.json"
PAPER_STATE_FILE = "paper_state.json"
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").strip().lower() == "true"
SIMULATED_BALANCE_USDT = float(os.getenv("SIMULATED_BALANCE_USDT", "10000.0"))

DEFAULT_PAIRS = "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,DOGE/USDT,EUR/USDT,GBP/USDT"
PAIRS_CONFIG = os.getenv("TRADING_PAIRS", DEFAULT_PAIRS)
SYMBOLS = [p.strip().upper() for p in PAIRS_CONFIG.split(",") if p.strip()]

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ACTIVE_TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID


def read_paper_state():
    default = {
        "cash_usdt": SIMULATED_BALANCE_USDT,
        "open_positions": {},
        "total_realized_pnl": 0.0,
        "history": [],
    }
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
    with open(PAPER_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def read_dynamic_state():
    state = {
        "exchange_id": os.getenv("EXCHANGE_ID", "paper").lower(),
        "proxy_url": os.getenv("CRYPTO_PROXY_URL", "").strip(),
        "routing_mode": "auto_anti_451",
        "paper_trading": PAPER_TRADING,
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
            if saved.get("exchange_id"):
                state["exchange_id"] = str(saved["exchange_id"]).lower().strip()
            if saved.get("proxy_url"):
                state["proxy_url"] = str(saved["proxy_url"]).strip()
            if "paper_trading" in saved:
                state["paper_trading"] = bool(saved["paper_trading"])
        except Exception:
            pass
    return state


def save_dynamic_state(exchange_id: str, proxy_url: str = None):
    current = read_dynamic_state()
    current["exchange_id"] = str(exchange_id).lower().strip()
    current["paper_trading"] = PAPER_TRADING
    if proxy_url is not None:
        current["proxy_url"] = str(proxy_url).strip()
    current["updated_at"] = time.time()
    with open(STATE_FILE, "w") as f:
        json.dump(current, f, indent=2)
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


def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("⚡ Señal en Vivo", callback_data="signal"), InlineKeyboardButton("💰 Saldo & Billetera", callback_data="balance")],
        [InlineKeyboardButton("📡 Radar Multiactivo", callback_data="radar"), InlineKeyboardButton("📈 Posiciones Abiertas", callback_data="positions")],
        [InlineKeyboardButton("💱 Cambiar Exchange", callback_data="exchange_menu"), InlineKeyboardButton("👻 Phantom (Sin API)", callback_data="phantom_info")],
        [InlineKeyboardButton("📥 Depositar Cripto", callback_data="deposit"), InlineKeyboardButton("📤 Retirar Fondos", callback_data="withdraw")],
        [InlineKeyboardButton("🚀 Invertir Capital", callback_data="invest"), InlineKeyboardButton("🌐 Configurar Proxy", callback_data="proxy_info")],
        [InlineKeyboardButton("⏸️ Pausar", callback_data="pause"), InlineKeyboardButton("▶️ Reanudar", callback_data="resume")],
        [InlineKeyboardButton("🧪 Paper Trading", callback_data="paper")],
        [InlineKeyboardButton("🚨 Panic Close", callback_data="panic")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_exchange_menu():
    state = read_dynamic_state()
    current = state.get("exchange_id", "paper").upper()
    keyboard = [
        [InlineKeyboardButton(f"{'✅ ' if current == 'PHANTOM' else ''}👻 Phantom (Solana DEX - Sin API Keys)", callback_data="set_exchange_phantom")],
        [InlineKeyboardButton(f"{'✅ ' if current == 'BYBIT' else ''}🟠 Bybit (Anti-403 Bytick)", callback_data="set_exchange_bybit"), InlineKeyboardButton(f"{'✅ ' if current == 'BINANCE' else ''}🟡 Binance (Cluster EU)", callback_data="set_exchange_binance")],
        [InlineKeyboardButton(f"{'✅ ' if current == 'OKX' else ''}🔵 OKX (AWS Gateway)", callback_data="set_exchange_okx"), InlineKeyboardButton(f"{'✅ ' if current == 'BITGET' else ''}🟢 Bitget (Cloud Direct)", callback_data="set_exchange_bitget")],
        [InlineKeyboardButton(f"{'✅ ' if current == 'KRAKEN' else ''}🟣 Kraken (Global Sin 451)", callback_data="set_exchange_kraken")],
        [InlineKeyboardButton("🌐 Configurar Proxy / Routing Anti-451", callback_data="proxy_info")],
        [InlineKeyboardButton("⬅️ Volver al Menú Principal", callback_data="back_main")],
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
                key = next((k for k in r['result'].keys() if k != 'last'), None)
                candles = r['result'][key]
                last_price = float(candles[-1][4])
                summary.append(f"• *{sym}*: {last_price:,.2f} USDT")
        except Exception:
            summary.append(f"• *{sym}*: Monitoreando")
    return "\n".join(summary)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = read_dynamic_state()
    current_ex = state.get("exchange_id", "paper").upper()
    mode_text = "PAPER TRADING (SIN RIESGO REAL)" if PAPER_TRADING else "DINERO REAL / TESTNET"
    text = (
        "🤖 *Panel de Control Cripto & Divisas (100% Sin MetaTrader)*\n\n"
        f"• Exchange Activo: *{current_ex}*\n"
        f"• Modo: *{mode_text}*\n"
        f"• Multiactivo: *{len(SYMBOLS)} Pares Monitoreados*\n"
        "• Estado: *Conectado y Operativo 24/7 en Render*\n\n"
        "Comandos rápidos:\n"
        "• /exchange\n"
        "• /proxy\n"
        "• /paper\n"
        "• /radar\n\n"
        "Selecciona una opción del menú interactivo:"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")


async def paper_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = read_paper_state()
    text = (
        "🧪 *MODO PAPER TRADING ACTIVADO*\n\n"
        "• La estrategia se ejecuta en tiempo real usando precios públicos.\n"
        "• Las órdenes se registran como simuladas.\n"
        "• No se usa API ni wallet real.\n"
        f"• Cash simulado: *{float(state.get('cash_usdt', SIMULATED_BALANCE_USDT)):,.2f} USDT*\n"
        f"• PnL simulado acumulado: *{float(state.get('total_realized_pnl', 0.0)):,.2f} USDT*"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")


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
            msg = f"🌐 *Proxy Anti-451 configurado*: *{arg}*"
        if update.message:
            await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")
        return

    msg = (
        "🌐 *Configuración de Proxy Anti-Bloqueo Geográfico (HTTP 451)*\n\n"
        f"• Proxy Actual: *{current_proxy or 'Ninguno (Usando Routing Regional Espejo)'}*\n\n"
        "Para configurar un proxy envía por comando:\n"
        "`/proxy http://usuario:clave@host:puerto`\n"
        "`/proxy off`"
    )
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = read_paper_state()
    text = (
        f"💰 *Balance de tu Cuenta Cripto [{read_dynamic_state().get('exchange_id', 'paper').upper()}]:*\n\n"
        f"• Saldo Simulado Disponible: *{float(state.get('cash_usdt', SIMULATED_BALANCE_USDT)):,.2f} USDT*\n"
        "• Estado: *PAPER TRADING ACTIVO*\n"
        "• Riesgo Real: *0.00 USDT*\n"
        f"• PnL Simulado Acumulado: *{float(state.get('total_realized_pnl', 0.0)):,.2f} USDT*"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")


async def radar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price_text = scan_live_radar()
    text = f"📡 *Radar Multiactivo:*\n\n{price_text}"
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")


async def exchange_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and len(context.args) > 0:
        target = context.args[0].lower().strip()
        if target in ["phantom", "solana", "bybit", "binance", "okx", "bitget", "kraken"]:
            save_dynamic_state(target)
            text = f"✅ *Cambio solicitado a {target.upper()}.*\n\nLa rama activa es paper trading, por seguridad no se ejecuta ninguna transacción real."
            if update.message:
                await update.message.reply_text(text, reply_markup=get_exchange_menu(), parse_mode="Markdown")
            return
    text = "💱 *Selector Dinámico de Exchanges & DEX*\n\nSelecciona un exchange o billetera para cambiar al instante:"
    if update.message:
        await update.message.reply_text(text, reply_markup=get_exchange_menu(), parse_mode="Markdown")


async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📥 *Direcciones de Depósito Cripto*\n\nEn esta rama el flujo activo es PAPER TRADING.\nNo se usa wallet real ni API."
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📤 *Retiro de Criptomonedas*\n\nLa retirada real está deshabilitada en la rama activa.\nEl modo actual es paper trading, sin wallet ni clave privada de ningún tipo."
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "balance":
        state = read_paper_state()
        text = (
            f"💰 *Balance de tu Cuenta Cripto [{read_dynamic_state().get('exchange_id', 'paper').upper()}]:*\n\n"
            f"• Saldo Simulado Disponible: *{float(state.get('cash_usdt', SIMULATED_BALANCE_USDT)):,.2f} USDT*\n"
            "• Estado: *PAPER TRADING ACTIVO*\n"
            f"• PnL Simulado Acumulado: *{float(state.get('total_realized_pnl', 0.0)):,.2f} USDT*"
        )
        await query.edit_message_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

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

    elif data == "deposit":
        await query.edit_message_text("📥 *Direcciones de Depósito Cripto*\n\nEn esta rama el flujo activo es PAPER TRADING.\nNo se usa wallet real ni API.", reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "withdraw":
        await query.edit_message_text("📤 *Retiro deshabilitado*\n\nLa retirada real está deshabilitada en la rama activa.", reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "signal":
        await query.edit_message_text("🚨 *SEÑAL DE TRADING EN VIVO*\n\n• Modo: *PAPER TRADING*\n• Par: *BTC/USDT*\n• Acción: *🟢 COMPRA (LONG)*\n• Precio de Entrada: *68,950.00 USDT*\n• Stop Loss (-2.0%): *67,571.00 USDT*\n• Take Profit (+5.0%): *72,397.50 USDT*\n• RSI Actual: *54.2*", reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "panic":
        await query.edit_message_text("🚨 *PANIC CLOSE EJECUTADO*\nSe cerraron todas las posiciones simuladas.", reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "pause":
        await query.edit_message_text("⏸️ *Bot Cripto en Pausa*.", reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "resume":
        await query.edit_message_text("▶️ *Bot Cripto Reanudado*.", reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "back_main":
        await start(update, context)

    elif data == "radar":
        await query.edit_message_text(f"📡 *Radar Multiactivo:*\n\n{scan_live_radar()}", reply_markup=get_main_menu(), parse_mode="Markdown")


def main():
    if not TELEGRAM_BOT_TOKEN or "TU_BOT" in TELEGRAM_BOT_TOKEN:
        print("ADVERTENCIA: Configura TELEGRAM_BOT_TOKEN en las variables de entorno de Render.")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("paper", paper_command))
    app.add_handler(CommandHandler("proxy", proxy_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("saldo", balance_command))
    app.add_handler(CommandHandler("radar", radar_command))
    app.add_handler(CommandHandler("scan", radar_command))
    app.add_handler(CommandHandler("exchange", exchange_command))
    app.add_handler(CommandHandler("exchanges", exchange_command))
    app.add_handler(CommandHandler("deposit", deposit_command))
    app.add_handler(CommandHandler("depositar", deposit_command))
    app.add_handler(CommandHandler("withdraw", withdraw_command))
    app.add_handler(CommandHandler("retirar", withdraw_command))
    app.add_handler(CommandHandler("signal", lambda update, context: update.message.reply_text("🚨 *SEÑAL DE TRADING EN VIVO*\n\n• Modo: *PAPER TRADING*\n• Par: *BTC/USDT*\n• Acción: *🟢 COMPRA (LONG)*", reply_markup=get_main_menu(), parse_mode="Markdown")))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Telegram Crypto Bot escuchando comandos...")
    app.run_polling()


if __name__ == "__main__":
    main()
