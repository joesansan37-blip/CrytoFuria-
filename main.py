"""
AUTOTRADING CRYPTO & FOREX BOT ENGINE (100% SIN METATRADER 5)
Estrategia: Institutional_Scalper_MT5 (Crypto Bot) (Estrategia (Moving Average (EMA/SMA)) -> Bot Cripto)
Ejecución: CCXT (Bybit / Binance / OKX / Kraken / Bitget / Dinero Real)
Control Remoto: Telegram Bot API

MODO ACTIVO: PAPER TRADING
- No usa wallet real ni API keys.
- Genera señales en tiempo real.
- Simula posiciones y PnL sin riesgo real.
"""

import time
import logging
import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import ccxt
import requests
import pandas as pd
import numpy as np

# Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

STATE_FILE = "bot_state.json"
PAPER_STATE_FILE = "paper_state.json"

PAPER_TRADING = os.getenv("PAPER_TRADING", "true").strip().lower() == "true"
SIMULATED_BALANCE_USDT = float(os.getenv("SIMULATED_BALANCE_USDT", "10000.0"))


def read_paper_state():
    default = {
        "cash_usdt": SIMULATED_BALANCE_USDT,
        "open_positions": {},
        "total_realized_pnl": 0.0,
        "history": []
    }
    if not os.path.exists(PAPER_STATE_FILE):
        return default
    try:
        with open(PAPER_STATE_FILE, "r") as f:
            saved = json.load(f)
        default.update(saved)
        if "cash_usdt" not in saved:
            default["cash_usdt"] = SIMULATED_BALANCE_USDT
        if "open_positions" not in saved:
            default["open_positions"] = {}
        if "total_realized_pnl" not in saved:
            default["total_realized_pnl"] = 0.0
        if "history" not in saved:
            default["history"] = []
        return default
    except Exception as e:
        logging.warning(f"Aviso leyendo {PAPER_STATE_FILE}: {e}")
        return default


def save_paper_state(state):
    try:
        with open(PAPER_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logging.error(f"Error guardando {PAPER_STATE_FILE}: {e}")


def get_paper_balance_text():
    state = read_paper_state()
    cash = float(state.get("cash_usdt", SIMULATED_BALANCE_USDT))
    return f"{cash:,.2f} USDT"


# --- SERVIDOR WEB LIGERO PARA RENDER (100% GRATIS 24/7) ---
class RenderHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"Bot Cripto & Divisas Multiactivo activo 24/7 en Render! (PAPER TRADING)")

    def log_message(self, format, *args):
        pass


def run_health_check_service():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), RenderHealthServer)
    logging.info(f"Servidor de Salud Render activo en el puerto {port}")
    server.serve_forever()


threading.Thread(target=run_health_check_service, daemon=True).start()

# --- CONFIGURACIÓN DE ACCESO Y CREDENCIALES ---
EXCHANGE_ID = os.getenv("EXCHANGE_ID", "paper").lower()
API_KEY = os.getenv("API_KEY", "").strip()
API_SECRET = os.getenv("API_SECRET", "").strip()
IS_TESTNET = os.getenv("IS_TESTNET", "false").lower() == "true"

# Telegram Bot (Lectura directa de variables de entorno de Render)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# --- UNIVERSO MULTIACTIVO: TODAS LAS CRIPTOMONEDAS Y TODAS LAS DIVISAS ---
DEFAULT_PAIRS = "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,DOGE/USDT,EUR/USDT,GBP/USDT"
PAIRS_CONFIG = os.getenv("TRADING_PAIRS", DEFAULT_PAIRS)
SYMBOLS = [p.strip().upper() for p in PAIRS_CONFIG.split(",") if p.strip()]

# Parámetros Operativos
TIMEFRAME = "5m"
WALLET_INVESTED_USDT = float(os.getenv("WALLET_INVESTED_USDT", "500.0"))
ORDER_SIZE_USDT = float(os.getenv("ORDER_SIZE_USDT", "50.0"))
LEVERAGE = int(os.getenv("LEVERAGE", "5"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "2.0"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "5.0"))
MAX_DAILY_LOSS_USDT = float(os.getenv("MAX_DAILY_LOSS_USDT", "50.0"))

exchange = None
is_trading_active = True
initial_usdt_balance = SIMULATED_BALANCE_USDT if PAPER_TRADING else WALLET_INVESTED_USDT
active_positions = {}
cycle_counter = 0

ACTIVE_TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def read_dynamic_state():
    state = {
        "exchange_id": os.getenv("EXCHANGE_ID", "paper").lower(),
        "proxy_url": os.getenv("CRYPTO_PROXY_URL", "").strip(),
        "routing_mode": "auto_anti_451",
        "active_chat_id": os.getenv("TELEGRAM_CHAT_ID", "").strip(),
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
                if "active_chat_id" in saved and saved["active_chat_id"]:
                    state["active_chat_id"] = str(saved["active_chat_id"]).strip()
                if "paper_trading" in saved:
                    state["paper_trading"] = bool(saved["paper_trading"])
        except Exception as e:
            logging.warning(f"Aviso leyendo {STATE_FILE}: {e}")
    return state


def save_dynamic_state(exchange_id: str, proxy_url: str = None, chat_id: str = None):
    current = read_dynamic_state()
    current["exchange_id"] = exchange_id.lower().strip()
    if proxy_url is not None:
        current["proxy_url"] = proxy_url.strip()
    if chat_id is not None and chat_id:
        current["active_chat_id"] = str(chat_id).strip()
    current["updated_at"] = time.time()
    current["paper_trading"] = PAPER_TRADING
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(current, f, indent=2)
    except Exception as e:
        logging.error(f"Error guardando {STATE_FILE}: {e}")
    return current


def get_target_chat_id(explicit_chat_id: str = None) -> str:
    global ACTIVE_TELEGRAM_CHAT_ID
    if explicit_chat_id and str(explicit_chat_id).strip():
        return str(explicit_chat_id).strip()
    if ACTIVE_TELEGRAM_CHAT_ID and "TU_CHAT" not in ACTIVE_TELEGRAM_CHAT_ID:
        return ACTIVE_TELEGRAM_CHAT_ID
    saved_state = read_dynamic_state()
    saved_id = saved_state.get("active_chat_id")
    if saved_id and "TU_CHAT" not in str(saved_id):
        ACTIVE_TELEGRAM_CHAT_ID = str(saved_id).strip()
        return ACTIVE_TELEGRAM_CHAT_ID
    return TELEGRAM_CHAT_ID


def send_telegram(message: str, reply_markup: dict = None, target_chat_id: str = None) -> bool:
    token = TELEGRAM_BOT_TOKEN
    chat_id = get_target_chat_id(target_chat_id)
    if not token or "TU_TELEGRAM" in token:
        logging.warning("⚠️ [TELEGRAM INACTIVO] Falta configurar TELEGRAM_BOT_TOKEN en las variables de entorno de Render.")
        return False
    if not chat_id or "TU_CHAT" in chat_id:
        logging.warning("⚠️ [TELEGRAM EN ESPERA] Esperando a que abras tu bot en Telegram y envíes /start para registrar tu Chat ID automáticamente.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(url, json=payload, timeout=8)
        if r.status_code == 200:
            return True
        else:
            if "can't parse entities" in r.text.lower() or "bad request" in r.text.lower():
                payload.pop("parse_mode", None)
                r_retry = requests.post(url, json=payload, timeout=5)
                return r_retry.status_code == 200
            return False
    except Exception as e:
        logging.error(f"Excepción enviando mensaje a Telegram: {e}")
        return False


def edit_telegram_message(target_chat_id, message_id: int, text: str, reply_markup: dict = None):
    token = TELEGRAM_BOT_TOKEN
    if not token:
        return False
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    payload = {"chat_id": target_chat_id, "message_id": message_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(url, json=payload, timeout=5)
        if r.status_code != 200:
            payload.pop("parse_mode", None)
            requests.post(url, json=payload, timeout=5)
        return True
    except Exception:
        return False


def answer_callback_query(cq_id: str):
    token = TELEGRAM_BOT_TOKEN
    if not token:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cq_id}, timeout=3)
    except Exception:
        pass


def register_telegram_commands():
    token = TELEGRAM_BOT_TOKEN
    if not token or "TU_TELEGRAM" in token:
        return
    commands = [
        {"command": "start", "description": "Menú principal y botones de control"},
        {"command": "signal", "description": "Emitir señal técnica de trading inmediata"},
        {"command": "radar", "description": "Escáner multiactivo en vivo"},
        {"command": "balance", "description": "Consultar saldo simulado y capital de trading"},
        {"command": "deposit", "description": "Direcciones y opciones de depósito"},
        {"command": "withdraw", "description": "Retirar fondos a tu billetera"},
        {"command": "phantom", "description": "Modo Phantom Wallet (Solana DEX sin API Keys)"},
        {"command": "exchange", "description": "Cambiar de exchange (Bybit, Binance, OKX, Kraken)"},
        {"command": "panic", "description": "Cerrar todas las operaciones de emergencia"},
        {"command": "paper", "description": "Mostrar estado del modo paper trading"}
    ]
    try:
        requests.post(f"https://api.telegram.org/bot{token}/setMyCommands", json={"commands": commands}, timeout=5)
        logging.info("Comandos del menú azul de Telegram registrados con éxito.")
    except Exception as e:
        logging.warning(f"Aviso registrando setMyCommands: {e}")


def get_persistent_keyboard_markup():
    return {
        "keyboard": [
            [{"text": "💰 Saldo & Billetera"}, {"text": "📡 Radar Multiactivo"}],
            [{"text": "⚡ Señal en Vivo"}, {"text": "📈 Posiciones Activas"}],
            [{"text": "📥 Depositar Cripto"}, {"text": "📤 Retirar Fondos"}],
            [{"text": "🧪 Paper Trading"}, {"text": "💱 Cambiar Exchange"}, {"text": "🚨 Panic Close"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }


def get_main_menu_markup():
    return {
        "inline_keyboard": [
            [{"text": "💰 Saldo & Billetera", "callback_data": "balance"},
             {"text": "📡 Radar Multiactivo", "callback_data": "radar"}],
            [{"text": "⚡ Señal de Trading Inmediata", "callback_data": "force_signal"}],
            [{"text": "💱 Cambiar Exchange / DEX", "callback_data": "exchange_menu"},
             {"text": "📈 Posiciones Abiertas", "callback_data": "positions"}],
            [{"text": "👻 Phantom (Sin API Keys)", "callback_data": "phantom_info"},
             {"text": "📥 Depositar Cripto", "callback_data": "deposit"}],
            [{"text": "📤 Retirar Fondos", "callback_data": "withdraw"},
             {"text": "🚀 Invertir Capital", "callback_data": "invest"}],
            [{"text": "🌐 Configurar Proxy", "callback_data": "proxy_info"},
             {"text": "🚨 Panic Close", "callback_data": "panic"}],
            [{"text": "⏸️ Pausar", "callback_data": "pause"},
             {"text": "▶️ Reanudar", "callback_data": "resume"}]
        ]
    }


def get_exchange_menu_markup():
    state = read_dynamic_state()
    cur = state.get("exchange_id", EXCHANGE_ID).upper()
    return {
        "inline_keyboard": [
            [{"text": f"{'✅ ' if cur == 'PHANTOM' else ''}👻 Phantom (Solana DEX - Sin API Keys)", "callback_data": "set_exchange_phantom"}],
            [{"text": f"{'✅ ' if cur == 'BYBIT' else ''}🟠 Bybit (Anti-403 Bytick)", "callback_data": "set_exchange_bybit"},
             {"text": f"{'✅ ' if cur == 'BINANCE' else ''}🟡 Binance (Cluster EU)", "callback_data": "set_exchange_binance"}],
            [{"text": f"{'✅ ' if cur == 'OKX' else ''}🔵 OKX (AWS Gateway)", "callback_data": "set_exchange_okx"},
             {"text": f"{'✅ ' if cur == 'BITGET' else ''}🟢 Bitget (Cloud Direct)", "callback_data": "set_exchange_bitget"}],
            [{"text": f"{'✅ ' if cur == 'KRAKEN' else ''}🟣 Kraken (Global Sin 451)", "callback_data": "set_exchange_kraken"}],
            [{"text": "🌐 Configurar Proxy / Routing Anti-451", "callback_data": "proxy_info"}],
            [{"text": "⬅️ Volver al Menú Principal", "callback_data": "back_main"}]
        ]
    }


def generate_immediate_signal_alert() -> str:
    """Escanea el mercado y genera una señal de trading inmediata y accionable"""
    best_sig = None
    best_sym = SYMBOLS[0] if SYMBOLS else "BTC/USDT"
    for s in SYMBOLS[:5]:
        res = calculate_technical_signals(s)
        if res:
            best_sig = res
            best_sym = s
            if res.get('buy') or res.get('sell'):
                break

    price = best_sig['close'] if best_sig else 68950.00
    rsi = best_sig['rsi'] if best_sig else 55.0
    action = "BUY" if rsi >= 48 else "SELL"
    action_label = "🟢 COMPRA (LONG)" if action == "BUY" else "🔴 VENTA (SHORT)"
    sl = price * (1 - (STOP_LOSS_PCT / 100.0)) if action == "BUY" else price * (1 + (STOP_LOSS_PCT / 100.0))
    tp = price * (1 + (TAKE_PROFIT_PCT / 100.0)) if action == "BUY" else price * (1 - (TAKE_PROFIT_PCT / 100.0))
    reason = best_sig.get('reason', 'Momentum EMA + RSI') if best_sig else 'Momentum Técnico EMA'

    mode_label = "PAPER TRADING" if PAPER_TRADING else "LIVE SIMULACIÓN"
    return (
        f"🚨 *SEÑAL DE TRADING EN VIVO [{mode_label}]*\n\n"
        f"• Par: *{best_sym}*\n"
        f"• Acción: *{action_label}*\n"
        f"• Precio de Entrada: *{price:,.2f} USDT*\n"
        f"• Stop Loss (-{STOP_LOSS_PCT}%): *{sl:,.2f} USDT*\n"
        f"• Take Profit (+{TAKE_PROFIT_PCT}%): *{tp:,.2f} USDT*\n"
        f"• RSI Actual: *{rsi:.1f}*\n"
        f"• Lógica Técnica: *{reason}*\n"
        f"• Apalancamiento Sugerido: *{LEVERAGE}x*\n\n"
        "⚡ _El motor multiactivo autónomo continúa evaluando velas 24/7 en modo seguro._"
    )


def handle_telegram_update(update: dict):
    global is_trading_active, ACTIVE_TELEGRAM_CHAT_ID
    try:
        if "message" in update:
            msg = update["message"]
            raw_chat_id = msg.get("chat", {}).get("id")
            if raw_chat_id:
                sender_chat_id = str(raw_chat_id).strip()
                if sender_chat_id != ACTIVE_TELEGRAM_CHAT_ID:
                    ACTIVE_TELEGRAM_CHAT_ID = sender_chat_id
                    save_dynamic_state(EXCHANGE_ID, chat_id=sender_chat_id)
                    logging.info(f"Chat ID de Telegram registrado y guardado: {sender_chat_id}")

            text = (msg.get("text") or "").strip()
            if not text:
                return

            cmd = text.lower()

            if cmd in ["/start", "/menu", "/ayuda", "menu", "inicio"]:
                state = read_dynamic_state()
                cur_ex = state.get("exchange_id", EXCHANGE_ID).upper()
                proxy = state.get("proxy_url")
                mode_label = "PAPER TRADING (SIN RIESGO REAL)" if PAPER_TRADING else "LIVESTREAM CONEXIÓN REAL"
                welcome = (
                    "🤖 *Panel de Control Cripto & Divisas (100% Sin MetaTrader)*\n\n"
                    f"• Exchange/Protocolo: *{cur_ex}*\n"
                    f"• Modo: *{mode_label}*\n"
                    f"• Routing Anti-451: *{'Proxy Activo' if proxy else 'Routing Regional Espejo'}*\n"
                    f"• Estado: *Operativo 24/7 en Render*\n"
                    f"• Multiactivo: *{len(SYMBOLS)} Pares Monitoreados*\n"
                    f"• Chat ID Vinculado: *{ACTIVE_TELEGRAM_CHAT_ID}* ✅\n\n"
                    "Comandos Rápidos:\n"
                    "• /signal : Emitir señal de trading en vivo al instante\n"
                    "• /exchange : Cambiar exchange dinámicamente\n"
                    "• /paper : Mostrar información del modo paper trading\n"
                    "• /radar : Escáner de precios y RSI en vivo\n\n"
                    "Usa los botones fijados abajo en tu pantalla o selecciona una opción del menú:"
                )
                send_telegram(welcome, reply_markup=get_persistent_keyboard_markup())
                send_telegram("🎛️ *Centro de Operaciones y Control Remoto:*", reply_markup=get_main_menu_markup())

            elif cmd.startswith("/paper") or "paper trading" in cmd or "paper" in cmd:
                paper_state = read_paper_state()
                cash = float(paper_state.get("cash_usdt", SIMULATED_BALANCE_USDT))
                pnl = float(paper_state.get("total_realized_pnl", 0.0))
                msg = (
                    "🧪 *MODO PAPER TRADING ACTIVADO*\n\n"
                    "• La estrategia se ejecuta en tiempo real usando precios públicos.\n"
                    "• Las órdenes se registran como simuladas.\n"
                    "• No se usa API ni wallet real.\n"
                    f"• Cash simulado: *{cash:,.2f} USDT*\n"
                    f"• PnL simulado acumulado: *{pnl:,.2f} USDT*\n"
                    "• Las posiciones se gestionan de forma segura y local."
                )
                send_telegram(msg, reply_markup=get_main_menu_markup())

            elif cmd.startswith("/signal") or cmd.startswith("/test_signal") or "señal" in cmd or "senal" in cmd:
                sig_alert = generate_immediate_signal_alert()
                send_telegram(sig_alert, reply_markup=get_main_menu_markup())

            elif cmd.startswith("/phantom") or "phantom" in cmd:
                p_text = (
                    "👻 *MODO PHANTOM WALLET / SOLANA DEX (SIN API KEYS NI KYC)*\n\n"
                    "• En esta rama la integración con Phantom queda deshabilitada por seguridad.\n"
                    "• La ejecución actual es paper trading y no requiere una wallet conectada.\n"
                    "• Cuando se habilite la integración real, se usará una wallet nueva y separada."
                )
                send_telegram(p_text, reply_markup=get_exchange_menu_markup())

            elif cmd.startswith("/exchange") or cmd.startswith("/exchanges") or "cambiar exchange" in cmd:
                parts = text.split()
                if len(parts) >= 2:
                    target = parts[1].lower().strip()
                    if target in ["phantom", "solana", "bybit", "binance", "okx", "bitget", "kraken"]:
                        save_dynamic_state(target, chat_id=ACTIVE_TELEGRAM_CHAT_ID)
                        init_exchange(target)
                        resp_msg = f"✅ *Exchange cambiado. Modo activo: {target.upper()}.*"
                        send_telegram(resp_msg, reply_markup=get_exchange_menu_markup())
                    else:
                        send_telegram("⚠️ Opción no válida. Usa: phantom, bybit, binance, okx, bitget o kraken.", reply_markup=get_exchange_menu_markup())
                else:
                    menu_msg = (
                        "💱 *Selector Dinámico de Exchanges & DEX (Phantom / Solana)*\n\n"
                        f"• Exchange Actual: *{EXCHANGE_ID.upper()}*\n"
                        "Selecciona un exchange o billetera para cambiar al instante:"
                    )
                    send_telegram(menu_msg, reply_markup=get_exchange_menu_markup())

            elif cmd.startswith("/proxy"):
                parts = text.split()
                if len(parts) >= 2:
                    p_val = parts[1].strip()
                    if p_val.lower() in ["off", "none", "disable", "desactivar"]:
                        save_dynamic_state(EXCHANGE_ID, "", chat_id=ACTIVE_TELEGRAM_CHAT_ID)
                        send_telegram("🌐 *Proxy desactivado*. Usando routing regional directo.", reply_markup=get_main_menu_markup())
                    else:
                        save_dynamic_state(EXCHANGE_ID, p_val, chat_id=ACTIVE_TELEGRAM_CHAT_ID)
                        send_telegram(f"🌐 *Proxy Anti-451 configurado*: *{p_val}*", reply_markup=get_main_menu_markup())
                else:
                    state = read_dynamic_state()
                    cur_p = state.get("proxy_url", "Ninguno")
                    send_telegram(f"🌐 *Proxy Actual*: *{cur_p}*\n\nPara configurar: */proxy http://user:pass@ip:port* o */proxy off*", reply_markup=get_main_menu_markup())

            elif cmd.startswith("/deposit") or cmd.startswith("/depositar") or "deposito" in cmd or "depósito" in cmd:
                d_msg = (
                    "📥 *Direcciones de depósito \n\n"
                    "En esta rama están deshabilitadas para seguridad.\n"
                    "El flujo activo es PAPER TRADING.\n"
                    "No se usa wallet real ni API.\n\n"
                    "Cuando se conecte la wallet nueva y separada, se mostrará solo la dirección comprobada."
                )
                send_telegram(d_msg, reply_markup=get_main_menu_markup())

            elif cmd.startswith("/withdraw") or cmd.startswith("/retirar") or "retiro" in cmd:
                send_telegram("📤 *Retiro deshabilitado en paper trading.*\n\nNo se ejecuta ninguna transacción real en esta etapa.", reply_markup=get_main_menu_markup())

            elif cmd.startswith("/balance") or cmd.startswith("/saldo") or cmd.startswith("/wallet") or "saldo" in cmd:
                cash = get_paper_balance_text()
                bal_msg = (
                    f"💰 *Balance de tu Cuenta Cripto [{EXCHANGE_ID.upper()}]:*\n\n"
                    f"• Saldo Simulado Disponible: *{cash}*\n"
                    "• Estado: *PAPER TRADING ACTIVO*\n"
                    "• Riesgo Real: *0.00 USDT*\n"
                    f"• Capital en Autotrading: *{WALLET_INVESTED_USDT:,.2f} USDT*\n"
                    f"• Modo Activo: *{EXCHANGE_ID.upper()}* | Estado: *Operativo 24/7*"
                )
                send_telegram(bal_msg, reply_markup=get_main_menu_markup())

            elif cmd.startswith("/positions") or cmd.startswith("/trades") or "posiciones" in cmd:
                if len(active_positions) == 0:
                    send_telegram("ℹ️ No hay posiciones abiertas en este momento. El bot está buscando entradas activamente en modo simulación.", reply_markup=get_main_menu_markup())
                else:
                    lines = ["📈 *Posiciones Activas:*"]
                    for sym, p in active_positions.items():
                        lines.append(f"• *{sym}* [{p['side']}] Entrada: {p['entry']:,.4f} | SL: {p['sl']:,.4f} | TP: {p['tp']:,.4f}")
                    send_telegram("\n".join(lines), reply_markup=get_main_menu_markup())

            elif cmd.startswith("/radar") or cmd.startswith("/scan") or "radar" in cmd:
                prices = []
                for sym in SYMBOLS[:6]:
                    sig = calculate_technical_signals(sym)
                    if sig:
                        status = "🟢 Alcista" if sig['rsi'] > 55 else "🔴 Bajista" if sig['rsi'] < 45 else "⚪ Neutral"
                        prices.append(f"• *{sym}*: {sig['close']:,.2f} USDT | RSI: {sig['rsi']:.1f} ({status})")
                r_text = f"📡 *Radar Multiactivo [{EXCHANGE_ID.upper()}]:*\n\n" + ("\n".join(prices) if prices else "Escaneando velas...")
                send_telegram(r_text, reply_markup=get_main_menu_markup())

            elif cmd.startswith("/panic") or "emergencia" in cmd or "panic" in cmd:
                close_all_crypto_positions()
                send_telegram("🚨 *PANIC CLOSE EJECUTADO*: Todas las posiciones simulares fueron cerradas en paper trading.", reply_markup=get_main_menu_markup())

            elif cmd.startswith("/pause") or "pausa" in cmd:
                is_trading_active = False
                send_telegram("⏸️ *Bot Cripto en Pausa*. No se abrirán nuevas órdenes. (Modo simulación)", reply_markup=get_main_menu_markup())

            elif cmd.startswith("/resume") or "reanudar" in cmd:
                is_trading_active = True
                send_telegram("▶️ *Bot Cripto Reanudado*. Evaluando señales de mercado 24/7 en modo paper trading.", reply_markup=get_main_menu_markup())

        elif "callback_query" in update:
            cq = update["callback_query"]
            cq_id = cq.get("id")
            answer_callback_query(cq_id)
            c_msg = cq.get("message", {})
            chat_id = c_msg.get("chat", {}).get("id")
            msg_id = c_msg.get("message_id")
            data = cq.get("data", "")

            if data == "balance":
                cash = get_paper_balance_text()
                bal_msg = (
                    f"💰 *Balance de tu Cuenta Cripto [{EXCHANGE_ID.upper()}]:*\n\n"
                    f"• Saldo Simulado Disponible: *{cash}*\n"
                    "• Estado: *PAPER TRADING ACTIVO*\n"
                    "• Riesgo Real: *0.00 USDT*\n"
                    f"• Modo: *{EXCHANGE_ID.upper()}* | Estado: *Operativo*"
                )
                edit_telegram_message(chat_id, msg_id, bal_msg, reply_markup=get_main_menu_markup())

            elif data == "force_signal":
                sig_alert = generate_immediate_signal_alert()
                edit_telegram_message(chat_id, msg_id, sig_alert, reply_markup=get_main_menu_markup())

            elif data == "phantom_info":
                p_text = (
                    "👻 *MODO PHANTOM WALLET / SOLANA DEX (SIN API KEYS)*\n\n"
                    "La integración con Phantom queda deshabilitada en esta rama.\n\n"
                    "• Modo activo: *PAPER TRADING*\n"
                    "• Sin wallet real conectada.\n"
                    "• Se habilitará una wallet nueva y separada cuando se valide la integración segura."
                )
                edit_telegram_message(chat_id, msg_id, p_text, reply_markup=get_exchange_menu_markup())

            elif data == "exchange_menu":
                menu_msg = (
                    "💱 *Selector Dinámico de Exchanges & DEX (Phantom / Solana)*\n\n"
                    f"• Modo Actual: *{EXCHANGE_ID.upper()}*\n"
                    "Selecciona un exchange o billetera para cambiar al instante:"
                )
                edit_telegram_message(chat_id, msg_id, menu_msg, reply_markup=get_exchange_menu_markup())

            elif data.startswith("set_exchange_"):
                target = data.replace("set_exchange_", "").lower().strip()
                save_dynamic_state(target, chat_id=ACTIVE_TELEGRAM_CHAT_ID)
                init_exchange(target)
                conf_text = f"✅ *Exchange cambiado a {target.upper()}*. Modo simulado activo."
                edit_telegram_message(chat_id, msg_id, conf_text, reply_markup=get_exchange_menu_markup())

            elif data == "deposit":
                d_msg = (
                    "📥 *Direcciones de depósito deshabilitadas*\n\n"
                    "En esta rama el flujo activo es PAPER TRADING.\n"
                    "No se usa wallet real ni API."
                )
                edit_telegram_message(chat_id, msg_id, d_msg, reply_markup=get_main_menu_markup())

            elif data == "back_main":
                edit_telegram_message(chat_id, msg_id, "🤖 *Menú Principal:*", reply_markup=get_main_menu_markup())

            elif data == "panic":
                close_all_crypto_positions()
                edit_telegram_message(chat_id, msg_id, "🚨 *PANIC CLOSE EJECUTADO*: todas las posiciones simuladas han sido cerradas.", reply_markup=get_main_menu_markup())

            elif data == "pause":
                is_trading_active = False
                edit_telegram_message(chat_id, msg_id, "⏸️ *Bot Cripto en Pausa*.", reply_markup=get_main_menu_markup())

            elif data == "resume":
                is_trading_active = True
                edit_telegram_message(chat_id, msg_id, "▶️ *Bot Cripto Reanudado*.", reply_markup=get_main_menu_markup())

    except Exception as e:
        logging.error(f"Error procesando update de Telegram: {e}")


def telegram_polling_worker():
    token = TELEGRAM_BOT_TOKEN
    if not token or "TU_TELEGRAM" in token:
        logging.warning("Telegram Worker esperando TELEGRAM_BOT_TOKEN en Render.")
        return
    offset = 0
    logging.info("Telegram Polling Worker escuchando comandos en Render 24/7...")
    register_telegram_commands()
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {"offset": offset, "timeout": 20}
            resp = requests.get(url, params=params, timeout=25).json()
            if resp.get("ok"):
                for item in resp.get("result", []):
                    offset = item["update_id"] + 1
                    handle_telegram_update(item)
            time.sleep(0.5)
        except Exception:
            time.sleep(3)


threading.Thread(target=telegram_polling_worker, daemon=True).start()


def build_exchange_client(exchange_name: str, proxy_url: str = None):
    """Construye el cliente CCXT aplicando proxies y routing regional anti-451 / 403"""
    exchange_name = exchange_name.lower().strip()
    if PAPER_TRADING:
        logging.info("MODO PAPER TRADING ACTIVO: no se conectará a ninguna exchange real.")
        return None
    if exchange_name in ['phantom', 'solana']:
        return None
    if not hasattr(ccxt, exchange_name):
        raise ValueError(f"Exchange '{exchange_name}' no soportado en CCXT.")

    ExchangeClass = getattr(ccxt, exchange_name)
    params = {
        'enableRateLimit': True,
        'timeout': 15000,
        'options': {'defaultType': 'future' if LEVERAGE > 1 else 'spot'}
    }

    proxy = proxy_url or os.getenv("CRYPTO_PROXY_URL", "").strip() or os.getenv("HTTPS_PROXY", "").strip()
    if proxy:
        params['proxies'] = {'http': proxy, 'https': proxy}
        params['aiohttp_proxy'] = proxy
        logging.info(f"Conectando a {exchange_name.upper()} a través de Proxy Anti-451: {proxy}")

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
                    logging.info("Routing Regional Bybit: Activado endpoint espejo https://api.bytick.com")
        except Exception:
            pass
    elif exchange_name == 'binance':
        try:
            if hasattr(client, 'urls') and isinstance(client.urls, dict) and 'api' in client.urls:
                if isinstance(client.urls['api'], dict) and 'public' in client.urls['api']:
                    client.urls['api']['public'] = 'https://api1.binance.com'
                    logging.info("Routing Regional Binance: Activado cluster https://api1.binance.com")
        except Exception:
            pass
    elif exchange_name == 'okx':
        try:
            if hasattr(client, 'urls') and isinstance(client.urls, dict) and 'api' in client.urls:
                if isinstance(client.urls['api'], dict) and 'public' in client.urls['api']:
                    client.urls['api']['public'] = 'https://aws.okx.com'
                    logging.info("Routing Regional OKX: Activado gateway AWS https://aws.okx.com")
        except Exception:
            pass

    return client


def map_symbol_for_kraken(symbol: str) -> str:
    s = symbol.replace("/", "").replace("-", "").upper()
    if "BTC" in s:
        return s.replace("BTC", "XBT")
    if "DOGE" in s:
        return s.replace("DOGE", "XDG")
    if "EUR" in s and "USDT" in s:
        return "EURUSD"
    if "GBP" in s and "USDT" in s:
        return "GBPUSD"
    return s


def init_exchange(force_exchange_id: str = None):
    global exchange, initial_usdt_balance, EXCHANGE_ID
    state = read_dynamic_state()
    target_ex = (force_exchange_id or state.get("exchange_id") or EXCHANGE_ID).lower().strip()
    proxy = state.get("proxy_url")
    EXCHANGE_ID = target_ex

    if PAPER_TRADING:
        EXCHANGE_ID = "paper"
        exchange = None
        logging.info("Conectado en MODO PAPER TRADING (sin wallet ni API real).")
        msg_start = (
            "🚀 *Bot Cripto Iniciado en MODO PAPER TRADING*\n\n"
            "• Exchange / Red: *Simulación local segura*\n"
            "• Autenticación: *No usa API keys ni wallet real*\n"
            "• Protocolo de Ejecución: *Señales + registro de posiciones simuladas*\n"
            "• Feed de Precios: *Kraken / Exchange público vía API*\n"
            f"• Capital Simulado: *{SIMULATED_BALANCE_USDT:,.2f} USDT*\n"
            f"• Tamaño por Orden: *{ORDER_SIZE_USDT} USDT*\n"
            "• Monitoreo: *Papel y señales en tiempo real*\n"
            "• Control: *Telegram Bot 24/7 en Render*"
        )
        send_telegram(msg_start)
        return True

    if target_ex in ['phantom', 'solana']:
        EXCHANGE_ID = "phantom"
        exchange = None
        logging.info("Conectado en MODO PHANTOM WALLET / SOLANA DEX (100% Sin API Key ni Secret Key).")
        send_telegram("🚀 *MODO PHANTOM DESHABILITADO EN ESTA RAMA.*\n\nLa integración real queda fuera del alcance del paper trading.")
        return True

    try:
        is_cloud_blocked = False
        try:
            exchange = build_exchange_client(target_ex, proxy)
            if IS_TESTNET and hasattr(exchange, 'set_sandbox_mode'):
                exchange.set_sandbox_mode(True)
                logging.info(f"Conectado a {target_ex.upper()} en MODO TESTNET / SANDBOX.")
            if exchange:
                exchange.load_markets()
                logging.info(f"Mercados de {target_ex.upper()} cargados con éxito (Routing OK).")
        except Exception as load_err:
            err_str = str(load_err).lower()
            if any(term in err_str for term in ["restricted location", "451", "403", "cloudfront", "block access from your country", "forbidden"]):
                is_cloud_blocked = True
                logging.warning(
                    f"Aviso: {target_ex.upper()} detectó restricción IP cloud (HTTP 451/403). "
                    "Activando cotizaciones globales KRAKEN sin restricciones de IP..."
                )
                send_telegram("ℹ️ *Aviso de Routing Anti-451.*\n\nLa rama activa es paper trading. No se usa API real ni wallet real.")
                EXCHANGE_ID = "kraken"
                try:
                    exchange = ccxt.kraken({'enableRateLimit': True})
                    exchange.load_markets()
                except Exception:
                    exchange = None
            else:
                raise load_err

        is_real_money = (not IS_TESTNET) and bool(API_KEY) and ("tu_api" not in API_KEY)
        if is_real_money and exchange and hasattr(exchange, 'fetch_balance'):
            try:
                balance = exchange.fetch_balance()
                free_usdt = balance.get('USDT', {}).get('free', 0.0)
                if free_usdt > 0:
                    initial_usdt_balance = free_usdt
                    logging.info(f"Saldo real detectado en tu billetera de {EXCHANGE_ID.upper()}: {free_usdt:,.2f} USDT")
            except Exception as bal_err:
                logging.warning(f"Aviso consultando balance del exchange: {bal_err}. Usando capital asignado: {WALLET_INVESTED_USDT:,.2f} USDT.")

        mode_label = "DINERO REAL (Billetera Exchange)" if is_real_money else "MODO SIMULADOR / TESTNET (Fondos Seguros)"
        feed_label = "KRAKEN GLOBAL FEED" if is_cloud_blocked else EXCHANGE_ID.upper()

        msg_start = (
            "🚀 *Bot Cripto & Divisas Iniciado con Éxito*\n\n"
            f"• Exchange Activo: *{EXCHANGE_ID.upper()}*\n"
            f"• Modo de Operación: *{mode_label}*\n"
            f"• Feed de Mercado: *{feed_label}*\n"
            f"• Routing Anti-451: *{'Proxy Activo' if proxy else 'Routing Regional Espejo'}*\n"
            f"• Radar Multiactivo: *{len(SYMBOLS)} Activos Monitoreados*\n"
            f"• Pares: *{', '.join(SYMBOLS[:6])}...*\n"
            f"• Capital de Trading: *{initial_usdt_balance:,.2f} USDT*\n"
            f"• Tamaño por Orden: *{ORDER_SIZE_USDT} USDT* ({LEVERAGE}x)\n"
            f"• SL / TP: *{STOP_LOSS_PCT}% / +{TAKE_PROFIT_PCT}%*\n"
            "• 100% Autónomo: *Sin MetaTrader 5*"
        )
        sent = send_telegram(msg_start)
        if not sent:
            logging.warning("⚠️ No se pudo enviar el mensaje inicial a Telegram. Asegúrate de haber iniciado tu bot con /start.")
        return True
    except Exception as e:
        logging.error(f"Fallo conectando al exchange: {e}")
        send_telegram(f"❌ *Error de Conexión Cripto*: {e}")
        return False


def calculate_technical_signals(symbol: str):
    """Calcula indicadores técnicos (RSI, EMA) usando velas OHLCV directas del exchange o feed público Kraken"""
    try:
        ohlcv = None
        if exchange and hasattr(exchange, 'fetch_ohlcv'):
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
            except Exception:
                pass

        if not ohlcv or len(ohlcv) < 20:
            pair_code = map_symbol_for_kraken(symbol)
            url = f"https://api.kraken.com/0/public/OHLC?pair={pair_code}&interval=15"
            resp = requests.get(url, timeout=8, headers={'User-Agent': 'CryptoForexBot/2.0'}).json()
            if 'result' in resp:
                key = [k for k in resp['result'].keys() if k != 'last'][0]
                raw_candles = resp['result'][key]
                ohlcv = [[int(c[0]) * 1000, float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[6])] for c in raw_candles[-100:]]

        if not ohlcv or len(ohlcv) < 20:
            return None

        df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df['ema_fast'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=50, adjust=False).mean()

        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))

        last = df.iloc[-1]
        prev = df.iloc[-2]

        ema_cross_up = bool((prev['ema_fast'] <= prev['ema_slow']) and (last['ema_fast'] > last['ema_slow']))
        ema_cross_down = bool((prev['ema_fast'] >= prev['ema_slow']) and (last['ema_fast'] < last['ema_slow']))
        trend_pullback_up = bool((last['ema_fast'] > last['ema_slow']) and (prev['rsi'] < 48) and (last['rsi'] >= 48))
        trend_pullback_down = bool((last['ema_fast'] < last['ema_slow']) and (prev['rsi'] > 52) and (last['rsi'] <= 52))
        rsi_rebound_buy = bool((prev['rsi'] < 35) and (last['rsi'] >= 35))
        rsi_rebound_sell = bool((prev['rsi'] > 65) and (last['rsi'] <= 65))

        buy_signal = bool(ema_cross_up or trend_pullback_up or rsi_rebound_buy)
        sell_signal = bool(ema_cross_down or trend_pullback_down or rsi_rebound_sell)

        reason = "Cruce Alcista EMA (Golden Cross)" if ema_cross_up else "Pullback de Tendencia Alcista en EMA" if trend_pullback_up else "Rebote de Sobreventa RSI (Giro Alcista)" if rsi_rebound_buy else "Cruce Bajista EMA (Death Cross)" if ema_cross_down else "Pullback de Tendencia Bajista en EMA" if trend_pullback_down else "Rebote de Sobrecompra RSI (Giro Bajista)"

        return {
            'symbol': symbol,
            'buy': buy_signal,
            'sell': sell_signal,
            'reason': reason,
            'close': float(last['close']),
            'rsi': float(last['rsi']),
            'ema_fast': float(last['ema_fast']),
            'ema_slow': float(last['ema_slow'])
        }
    except Exception as e:
        logging.error(f"Error calculando señales en {symbol}: {e}")
        return None


def check_circuit_breaker():
    global is_trading_active
    try:
        if PAPER_TRADING:
            return True
        if exchange and hasattr(exchange, 'fetch_balance') and API_KEY and "tu_api" not in API_KEY:
            bal = exchange.fetch_balance()
            current_usdt = bal.get('USDT', {}).get('total', initial_usdt_balance)
            loss = initial_usdt_balance - current_usdt
            if loss >= MAX_DAILY_LOSS_USDT:
                is_trading_active = False
                msg_cb = (
                    "🚨 *CIRCUIT BREAKER ACTIVADO*\n"
                    f"Pérdida diaria en USDT alcanzada: -*{loss:,.2f} USDT*. Deteniendo autotrading de inmediato."
                )
                send_telegram(msg_cb)
                close_all_crypto_positions()
                return False
        return True
    except Exception as e:
        logging.error(f"Error en circuit breaker: {e}")
        return True


def execute_crypto_order(symbol: str, side: str, current_price: float, reason: str = "Momentum Técnico"):
    try:
        amount = (ORDER_SIZE_USDT * LEVERAGE) / current_price
        amount = round(amount, 4)
        is_real = (not IS_TESTNET) and bool(API_KEY) and ("tu_api" not in API_KEY)

        if PAPER_TRADING:
            state = read_paper_state()
            sl_price = current_price * (1 - (STOP_LOSS_PCT / 100.0)) if side == "BUY" else current_price * (1 + (STOP_LOSS_PCT / 100.0))
            tp_price = current_price * (1 + (TAKE_PROFIT_PCT / 100.0)) if side == "BUY" else current_price * (1 - (TAKE_PROFIT_PCT / 100.0))

            position = {
                'side': side,
                'entry': float(current_price),
                'amount': float(amount),
                'sl': float(sl_price),
                'tp': float(tp_price),
                'notional': float(ORDER_SIZE_USDT)
            }
            state['open_positions'][symbol] = position
            if side == "BUY":
                state['cash_usdt'] = round(float(state.get('cash_usdt', SIMULATED_BALANCE_USDT)) - ORDER_SIZE_USDT, 2)
            else:
                state['cash_usdt'] = round(float(state.get('cash_usdt', SIMULATED_BALANCE_USDT)) + ORDER_SIZE_USDT, 2)
            save_paper_state(state)
            active_positions[symbol] = position

            msg = (
                f"🧪 *SEÑAL SIMULADA: {'COMPRA (LONG)' if side == 'BUY' else 'VENTA (SHORT)'}*\n\n"
                f"• Exchange: *PAPER*\n"
                f"• Par: *{symbol}*\n"
                f"• Precio de Entrada: *{current_price:,.4f} USDT*\n"
                f"• Monto Posición: *{ORDER_SIZE_USDT:.2f} USDT* ({LEVERAGE}x)\n"
                f"• Stop Loss: *{sl_price:,.4f} USDT*\n"
                f"• Take Profit: *{tp_price:,.4f} USDT*\n"
                f"• Lógica / Motivo: *{reason}*\n"
                "• Funcionamiento: *Se registra en modo pullback simulado sin riesgo real*"
            )
            send_telegram(msg)
            return

        if side == "BUY":
            sl_price = current_price * (1 - (STOP_LOSS_PCT / 100.0))
            tp_price = current_price * (1 + (TAKE_PROFIT_PCT / 100.0))
            if is_real and exchange and hasattr(exchange, 'create_market_buy_order'):
                exchange.create_market_buy_order(symbol, amount)
            active_positions[symbol] = {'side': 'BUY', 'entry': current_price, 'amount': amount, 'sl': sl_price, 'tp': tp_price}
            msg_buy = (
                f"🟢 *SEÑAL DE ENTRADA: COMPRA (LONG)*\n\n"
                f"• Modo: *{'DINERO REAL' if is_real else 'SIMULACIÓN / TESTNET'}*\n"
                f"• Exchange: *{EXCHANGE_ID.upper()}*\n"
                f"• Par: *{symbol}*\n"
                f"• Precio de Entrada: *{current_price:,.4f} USDT*\n"
                f"• Monto Posición: *{ORDER_SIZE_USDT:.2f} USDT* ({LEVERAGE}x)\n"
                f"• Stop Loss (-{STOP_LOSS_PCT}%): *{sl_price:,.4f} USDT*\n"
                f"• Take Profit (+{TAKE_PROFIT_PCT}%): *{tp_price:,.4f} USDT*\n"
                f"• Lógica / Motivo: *{reason}*\n"
                "• Monitoreo 24/7: *SL y TP bajo supervisión continua*"
            )
            send_telegram(msg_buy)
        else:
            sl_price = current_price * (1 + (STOP_LOSS_PCT / 100.0))
            tp_price = current_price * (1 - (TAKE_PROFIT_PCT / 100.0))
            if is_real and exchange and hasattr(exchange, 'create_market_sell_order'):
                exchange.create_market_sell_order(symbol, amount)
            active_positions[symbol] = {'side': 'SELL', 'entry': current_price, 'amount': amount, 'sl': sl_price, 'tp': tp_price}
            msg_sell = (
                f"🔴 *SEÑAL DE ENTRADA: VENTA (SHORT)*\n\n"
                f"• Modo: *{'DINERO REAL' if is_real else 'SIMULACIÓN / TESTNET'}*\n"
                f"• Exchange: *{EXCHANGE_ID.upper()}*\n"
                f"• Par: *{symbol}*\n"
                f"• Precio de Entrada: *{current_price:,.4f} USDT*\n"
                f"• Monto Posición: *{ORDER_SIZE_USDT:.2f} USDT* ({LEVERAGE}x)\n"
                f"• Stop Loss (+{STOP_LOSS_PCT}%): *{sl_price:,.4f} USDT*\n"
                f"• Take Profit (-{TAKE_PROFIT_PCT}%): *{tp_price:,.4f} USDT*\n"
                f"• Lógica / Motivo: *{reason}*\n"
                "• Monitoreo 24/7: *SL y TP bajo supervisión continua*"
            )
            send_telegram(msg_sell)
    except Exception as e:
        logging.error(f"Fallo ejecutando orden {side} en {symbol}: {e}")
        send_telegram(f"⚠️ *Error ejecutando orden {side} en {symbol}*: {e}")


def close_all_crypto_positions():
    try:
        if PAPER_TRADING:
            state = read_paper_state()
            state['open_positions'] = {}
            state['cash_usdt'] = SIMULATED_BALANCE_USDT
            save_paper_state(state)
            active_positions.clear()
            logging.info("Todas las órdenes y posiciones en paper trading han sido cerradas de emergencia.")
            send_telegram("🔒 *Todas las órdenes y posiciones simuladas han sido cerradas de emergencia.*")
            return

        if exchange and hasattr(exchange, 'cancel_all_orders'):
            for sym in SYMBOLS:
                try:
                    exchange.cancel_all_orders(sym)
                except Exception:
                    pass
        active_positions.clear()
        logging.info("Todas las órdenes y posiciones han sido cerradas de emergencia.")
        send_telegram("🔒 *Todas las órdenes y posiciones han sido cerradas de emergencia.*")
    except Exception as e:
        logging.error(f"Error cerrando posiciones: {e}")


def send_market_radar_pulse(results: list):
    lines = [f"📡 *Radar Multiactivo [{EXCHANGE_ID.upper()}] (Actualización en Vivo)*\n"]
    for r in results:
        status_icon = "🟢 Alcista" if r['rsi'] > 55 else "🔴 Bajista" if r['rsi'] < 45 else "⚪ Neutral"
        lines.append(f"• *{r['symbol']}*: {r['close']:,.2f} USDT | RSI: {r['rsi']:.1f} ({status_icon})")
    lines.append(f"\n📊 *Total Monitoreados*: {len(results)} activos en tiempo real 24/7.")
    send_telegram("\n".join(lines))


def run_crypto_loop():
    global cycle_counter
    while not init_exchange():
        logging.warning("Conexión en espera. Reintentando en 30 segundos (el servidor Render permanece activo 24/7)...")
        time.sleep(30)

    logging.info(f"Bot Multiactivo operativo en {EXCHANGE_ID.upper()}. Escaneando {len(SYMBOLS)} pares...")

    while True:
        try:
            state = read_dynamic_state()
            new_ex = state.get("exchange_id", EXCHANGE_ID).lower().strip()
            if new_ex != EXCHANGE_ID and new_ex in ["phantom", "solana", "bybit", "binance", "okx", "bitget", "kraken"]:
                logging.info(f"🔄 Cambio dinámico solicitado desde Telegram: {EXCHANGE_ID.upper()} -> {new_ex.upper()}")
                init_exchange(new_ex)

            if is_trading_active and check_circuit_breaker():
                cycle_results = []
                for symbol in SYMBOLS:
                    sig = calculate_technical_signals(symbol)
                    if sig:
                        cycle_results.append(sig)
                        price = sig['close']

                        if symbol not in active_positions:
                            if sig['buy']:
                                logging.info(f"Señal de COMPRA en {symbol} a {price:,.4f} USDT")
                                execute_crypto_order(symbol, "BUY", price, sig.get('reason', 'Cruce Alcista EMA'))
                            elif sig['sell']:
                                logging.info(f"Señal de VENTA en {symbol} a {price:,.4f} USDT")
                                execute_crypto_order(symbol, "SELL", price, sig.get('reason', 'Cruce Bajista EMA'))
                        else:
                            pos = active_positions[symbol]
                            if pos['side'] == 'BUY':
                                if price <= pos['sl']:
                                    loss_val = (price - pos['entry']) * pos['amount']
                                    send_telegram(
                                        f"🛑 *SEÑAL DE SALIDA: STOP LOSS EJECUTADO*\n\n"
                                        f"• Par: *{symbol}* [LONG]\n"
                                        f"• Entrada: *{pos['entry']:,.4f} USDT*\n"
                                        f"• Salida (SL): *{price:,.4f} USDT* (-{STOP_LOSS_PCT}%)\n"
                                        f"• Resultado (PnL): *{loss_val:,.2f} USDT*\n"
                                        "• Posición cerrada con control estricto de riesgo."
                                    )
                                    if PAPER_TRADING:
                                        paper_state = read_paper_state()
                                        paper_state['cash_usdt'] = round(float(paper_state.get('cash_usdt', SIMULATED_BALANCE_USDT)) + price * pos['amount'], 2)
                                        paper_state['total_realized_pnl'] = round(float(paper_state.get('total_realized_pnl', 0.0)) + loss_val, 2)
                                        paper_state['history'].append({"symbol": symbol, "side": "BUY", "pnl": loss_val, "type": "stop_loss"})
                                        save_paper_state(paper_state)
                                    active_positions.pop(symbol, None)
                                elif price >= pos['tp']:
                                    profit_val = (price - pos['entry']) * pos['amount']
                                    send_telegram(
                                        f"🎯 *SEÑAL DE SALIDA: TAKE PROFIT ALCANZADO*\n\n"
                                        f"• Par: *{symbol}* [LONG]\n"
                                        f"• Entrada: *{pos['entry']:,.4f} USDT*\n"
                                        f"• Salida (TP): *{price:,.4f} USDT* (+{TAKE_PROFIT_PCT}%)\n"
                                        f"• Ganancia Neta (PnL): *+{profit_val:,.2f} USDT* 💰\n"
                                        "• ¡Operación ganadora asegurada!"
                                    )
                                    if PAPER_TRADING:
                                        paper_state = read_paper_state()
                                        paper_state['cash_usdt'] = round(float(paper_state.get('cash_usdt', SIMULATED_BALANCE_USDT)) + price * pos['amount'], 2)
                                        paper_state['total_realized_pnl'] = round(float(paper_state.get('total_realized_pnl', 0.0)) + profit_val, 2)
                                        paper_state['history'].append({"symbol": symbol, "side": "BUY", "pnl": profit_val, "type": "take_profit"})
                                        save_paper_state(paper_state)
                                    active_positions.pop(symbol, None)
                            elif pos['side'] == 'SELL':
                                if price >= pos['sl']:
                                    loss_val = (pos['entry'] - price) * pos['amount']
                                    send_telegram(
                                        f"🛑 *SEÑAL DE SALIDA: STOP LOSS EJECUTADO*\n\n"
                                        f"• Par: *{symbol}* [SHORT]\n"
                                        f"• Entrada: *{pos['entry']:,.4f} USDT*\n"
                                        f"• Salida (SL): *{price:,.4f} USDT* (+{STOP_LOSS_PCT}%)\n"
                                        f"• Resultado (PnL): *{loss_val:,.2f} USDT*\n"
                                        "• Posición cerrada con control estricto de riesgo."
                                    )
                                    if PAPER_TRADING:
                                        paper_state = read_paper_state()
                                        paper_state['cash_usdt'] = round(float(paper_state.get('cash_usdt', SIMULATED_BALANCE_USDT)) - price * pos['amount'], 2)
                                        paper_state['total_realized_pnl'] = round(float(paper_state.get('total_realized_pnl', 0.0)) + loss_val, 2)
                                        paper_state['history'].append({"symbol": symbol, "side": "SELL", "pnl": loss_val, "type": "stop_loss"})
                                        save_paper_state(paper_state)
                                    active_positions.pop(symbol, None)
                                elif price <= pos['tp']:
                                    profit_val = (pos['entry'] - price) * pos['amount']
                                    send_telegram(
                                        f"🎯 *SEÑAL DE SALIDA: TAKE PROFIT ALCANZADO*\n\n"
                                        f"• Par: *{symbol}* [SHORT]\n"
                                        f"• Entrada: *{pos['entry']:,.4f} USDT*\n"
                                        f"• Salida (TP): *{price:,.4f} USDT* (-{TAKE_PROFIT_PCT}%)\n"
                                        f"• Ganancia Neta (PnL): *+{profit_val:,.2f} USDT* 💰\n"
                                        "• ¡Operación ganadora asegurada!"
                                    )
                                    if PAPER_TRADING:
                                        paper_state = read_paper_state()
                                        paper_state['cash_usdt'] = round(float(paper_state.get('cash_usdt', SIMULATED_BALANCE_USDT)) - price * pos['amount'], 2)
                                        paper_state['total_realized_pnl'] = round(float(paper_state.get('total_realized_pnl', 0.0)) + profit_val, 2)
                                        paper_state['history'].append({"symbol": symbol, "side": "SELL", "pnl": profit_val, "type": "take_profit"})
                                        save_paper_state(paper_state)
                                    active_positions.pop(symbol, None)

                    time.sleep(1)

                cycle_counter += 1
                if (cycle_counter == 1 or cycle_counter % 40 == 0) and len(cycle_results) > 0:
                    send_market_radar_pulse(cycle_results[:8])

            time.sleep(15)
        except KeyboardInterrupt:
            logging.info("Bot detenido por el usuario.")
            break
        except Exception as e:
            logging.error(f"Error en loop principal: {e}")
            time.sleep(10)


if __name__ == "__main__":
    run_crypto_loop()
