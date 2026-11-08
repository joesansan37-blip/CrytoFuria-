"""
AUTOTRADING CRYPTO & FOREX BOT ENGINE (PAPER TRADING ONLY)
Safe mode: signals only, no API keys, no wallet real, no real orders.
"""

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

STATE_FILE = "bot_state.json"
PAPER_STATE_FILE = "paper_state.json"
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").strip().lower() == "true"
SIMULATED_BALANCE_USDT = float(os.getenv("SIMULATED_BALANCE_USDT", "10000.0"))

DEFAULT_PAIRS = "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,DOGE/USDT,EUR/USDT,GBP/USDT"
PAIRS_CONFIG = os.getenv("TRADING_PAIRS", DEFAULT_PAIRS)
SYMBOLS = [p.strip().upper() for p in PAIRS_CONFIG.split(",") if p.strip()]

TIMEFRAME = "5m"
WALLET_INVESTED_USDT = float(os.getenv("WALLET_INVESTED_USDT", "500.0"))
ORDER_SIZE_USDT = float(os.getenv("ORDER_SIZE_USDT", "50.0"))
LEVERAGE = int(os.getenv("LEVERAGE", "5"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "2.0"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "5.0"))
MAX_DAILY_LOSS_USDT = float(os.getenv("MAX_DAILY_LOSS_USDT", "50.0"))

EXCHANGE_ID = os.getenv("EXCHANGE_ID", "paper").lower().strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ACTIVE_TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID

exchange = None
is_trading_active = True
cycle_counter = 0
active_positions = {}


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
        default["cash_usdt"] = float(saved.get("cash_usdt", default["cash_usdt"]))
        default["open_positions"] = saved.get("open_positions", {})
        default["total_realized_pnl"] = float(saved.get("total_realized_pnl", 0.0))
        default["history"] = saved.get("history", [])
        return default
    except Exception as exc:
        logging.warning(f"Aviso leyendo {PAPER_STATE_FILE}: {exc}")
        return default


def save_paper_state(state):
    try:
        with open(PAPER_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as exc:
        logging.error(f"Error guardando {PAPER_STATE_FILE}: {exc}")


def read_dynamic_state():
    state = {
        "exchange_id": EXCHANGE_ID,
        "proxy_url": os.getenv("CRYPTO_PROXY_URL", "").strip(),
        "routing_mode": "auto_anti_451",
        "active_chat_id": ACTIVE_TELEGRAM_CHAT_ID,
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
            if saved.get("active_chat_id"):
                state["active_chat_id"] = str(saved["active_chat_id"]).strip()
            if "paper_trading" in saved:
                state["paper_trading"] = bool(saved["paper_trading"])
        except Exception as exc:
            logging.warning(f"Aviso leyendo {STATE_FILE}: {exc}")
    return state


def save_dynamic_state(exchange_id: str, proxy_url: str = None, chat_id: str = None):
    current = read_dynamic_state()
    current["exchange_id"] = str(exchange_id).lower().strip()
    current["paper_trading"] = PAPER_TRADING
    if proxy_url is not None:
        current["proxy_url"] = str(proxy_url).strip()
    if chat_id and str(chat_id).strip():
        current["active_chat_id"] = str(chat_id).strip()
    current["updated_at"] = time.time()
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(current, f, indent=2)
    except Exception as exc:
        logging.error(f"Error guardando {STATE_FILE}: {exc}")
    return current


def get_target_chat_id(explicit_chat_id: str = None) -> str:
    global ACTIVE_TELEGRAM_CHAT_ID
    if explicit_chat_id and str(explicit_chat_id).strip():
        ACTIVE_TELEGRAM_CHAT_ID = str(explicit_chat_id).strip()
        return ACTIVE_TELEGRAM_CHAT_ID
    saved = read_dynamic_state()
    if saved.get("active_chat_id"):
        ACTIVE_TELEGRAM_CHAT_ID = str(saved["active_chat_id"]).strip()
        return ACTIVE_TELEGRAM_CHAT_ID
    return ACTIVE_TELEGRAM_CHAT_ID


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


def get_paper_balance_text():
    state = read_paper_state()
    return f"{float(state.get('cash_usdt', SIMULATED_BALANCE_USDT)):,.2f} USDT"


def send_telegram(message: str, reply_markup: dict = None, target_chat_id: str = None) -> bool:
    token = TELEGRAM_BOT_TOKEN
    chat_id = get_target_chat_id(target_chat_id)
    if not token or "TU_TELEGRAM" in token:
        logging.warning("TELEGRAM INACTIVO: falta TELEGRAM_BOT_TOKEN")
        return False
    if not chat_id or "TU_CHAT" in chat_id:
        logging.warning("TELEGRAM EN ESPERA: no hay Chat ID válido")
        return False

    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=8)
        if r.status_code == 200:
            return True
        if "bad request" in r.text.lower() or "can't parse" in r.text.lower():
            payload.pop("parse_mode", None)
            rr = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=5)
            return rr.status_code == 200
        return False
    except Exception as exc:
        logging.error(f"Error enviando Telegram: {exc}")
        return False


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


def calculate_technical_signals(symbol: str):
    try:
        pair_code = map_symbol_for_kraken(symbol)
        url = f"https://api.kraken.com/0/public/OHLC?pair={pair_code}&interval=15"
        resp = requests.get(url, timeout=8, headers={"User-Agent": "CryptoForexBot/2.0"}).json()
        if "result" not in resp:
            return None
        key = next((k for k in resp["result"].keys() if k != "last"), None)
        if not key:
            return None
        raw = resp["result"][key]
        ohlcv = [[int(c[0]) * 1000, float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[6])] for c in raw[-100:]]
        if len(ohlcv) < 20:
            return None

        df = pd.DataFrame(ohlcv, columns=["time", "open", "high", "low", "close", "volume"])
        df["ema_fast"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=50, adjust=False).mean()

        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df["rsi"] = 100 - (100 / (1 + rs))

        last = df.iloc[-1]
        prev = df.iloc[-2]

        ema_cross_up = bool((prev["ema_fast"] <= prev["ema_slow"]) and (last["ema_fast"] > last["ema_slow"]))
        ema_cross_down = bool((prev["ema_fast"] >= prev["ema_slow"]) and (last["ema_fast"] < last["ema_slow"]))
        trend_pullback_up = bool((last["ema_fast"] > last["ema_slow"]) and (prev["rsi"] < 48) and (last["rsi"] >= 48))
        trend_pullback_down = bool((last["ema_fast"] < last["ema_slow"]) and (prev["rsi"] > 52) and (last["rsi"] <= 52))
        rsi_rebound_buy = bool((prev["rsi"] < 35) and (last["rsi"] >= 35))
        rsi_rebound_sell = bool((prev["rsi"] > 65) and (last["rsi"] <= 65))

        buy_signal = bool(ema_cross_up or trend_pullback_up or rsi_rebound_buy)
        sell_signal = bool(ema_cross_down or trend_pullback_down or rsi_rebound_sell)

        reason = (
            "Cruce Alcista EMA (Golden Cross)" if ema_cross_up else
            "Pullback de Tendencia Alcista en EMA" if trend_pullback_up else
            "Rebote de Sobreventa RSI (Giro Alcista)" if rsi_rebound_buy else
            "Cruce Bajista EMA (Death Cross)" if ema_cross_down else
            "Pullback de Tendencia Bajista en EMA" if trend_pullback_down else
            "Rebote de Sobrecompra RSI (Giro Bajista)"
        )

        return {
            "symbol": symbol,
            "buy": buy_signal,
            "sell": sell_signal,
            "reason": reason,
            "close": float(last["close"]),
            "rsi": float(last["rsi"]),
            "ema_fast": float(last["ema_fast"]),
            "ema_slow": float(last["ema_slow"]),
        }
    except Exception as exc:
        logging.error(f"Error calculando señales en {symbol}: {exc}")
        return None


def ensure_paper_position(symbol, side, entry, amount, sl, tp):
    state = read_paper_state()
    state["open_positions"] = state.get("open_positions", {})
    state["open_positions"][symbol] = {
        "side": side,
        "entry": float(entry),
        "amount": float(amount),
        "sl": float(sl),
        "tp": float(tp),
        "notional": float(ORDER_SIZE_USDT),
    }
    if side == "BUY":
        state["cash_usdt"] = float(state.get("cash_usdt", SIMULATED_BALANCE_USDT)) - float(ORDER_SIZE_USDT)
    else:
        state["cash_usdt"] = float(state.get("cash_usdt", SIMULATED_BALANCE_USDT)) + float(ORDER_SIZE_USDT)
    save_paper_state(state)
    return state


def close_paper_position(symbol, exit_price, pnl):
    state = read_paper_state()
    pos = state.get("open_positions", {}).pop(symbol, None)
    if not pos:
        return
    state["cash_usdt"] = float(state.get("cash_usdt", SIMULATED_BALANCE_USDT)) + float(exit_price) * float(pos.get("amount", 0.0))
    state["total_realized_pnl"] = float(state.get("total_realized_pnl", 0.0)) + float(pnl)
    state["history"].append({
        "symbol": symbol,
        "side": pos.get("side"),
        "pnl": float(pnl),
        "exit_price": float(exit_price),
        "timestamp": int(time.time()),
    })
    save_paper_state(state)


def execute_crypto_order(symbol: str, side: str, current_price: float, reason: str = "Momentum Técnico"):
    if not PAPER_TRADING:
        logging.info("Ejecución real deshabilitada: rama paper-trading-only")
        return

    amount = (ORDER_SIZE_USDT * LEVERAGE) / current_price
    amount = round(amount, 4)
    sl_price = current_price * (1 - (STOP_LOSS_PCT / 100.0)) if side == "BUY" else current_price * (1 + (STOP_LOSS_PCT / 100.0))
    tp_price = current_price * (1 + (TAKE_PROFIT_PCT / 100.0)) if side == "BUY" else current_price * (1 - (TAKE_PROFIT_PCT / 100.0))

    ensure_paper_position(symbol, side, current_price, amount, sl_price, tp_price)
    active_positions[symbol] = {"side": side, "entry": current_price, "amount": amount, "sl": sl_price, "tp": tp_price}
    label = "COMPRA (LONG)" if side == "BUY" else "VENTA (SHORT)"
    send_telegram(
        f"🧪 *SEÑAL SIMULADA: {label}*\n\n"
        f"• Exchange: *PAPER*\n"
        f"• Par: *{symbol}*\n"
        f"• Precio de Entrada: *{current_price:,.4f} USDT*\n"
        f"• Monto Posición: *{ORDER_SIZE_USDT:.2f} USDT* ({LEVERAGE}x)\n"
        f"• Stop Loss: *{sl_price:,.4f} USDT*\n"
        f"• Take Profit: *{tp_price:,.4f} USDT*\n"
        f"• Lógica / Motivo: *{reason}*\n"
        "• Funcionamiento: *Se registra en modo seguro sin riesgo real*"
    )


def close_all_crypto_positions():
    if PAPER_TRADING:
        state = read_paper_state()
        state["open_positions"] = {}
        state["cash_usdt"] = SIMULATED_BALANCE_USDT
        save_paper_state(state)
        active_positions.clear()
        send_telegram("🔒 *Todas las posiciones simuladas han sido cerradas de emergencia.*")
        return
    active_positions.clear()


def check_circuit_breaker():
    return True


def send_market_radar_pulse(results: list):
    lines = ["📡 *Radar Multiactivo [PAPER] (Actualización en Vivo)*\n"]
    for item in results:
        status = "🟢 Alcista" if item["rsi"] > 55 else "🔴 Bajista" if item["rsi"] < 45 else "⚪ Neutral"
        lines.append(f"• *{item['symbol']}*: {item['close']:,.2f} USDT | RSI: {item['rsi']:.1f} ({status})")
    lines.append(f"\n📊 *Total Monitoreados*: {len(results)} activos en tiempo real 24/7.")
    send_telegram("\n".join(lines))


def run_crypto_loop():
    global cycle_counter
    logging.info("Bot operando en modo paper-trading. Escaneando señales en tiempo real.")
    while True:
        try:
            if is_trading_active and check_circuit_breaker():
                cycle_results = []
                for symbol in SYMBOLS:
                    sig = calculate_technical_signals(symbol)
                    if not sig:
                        continue
                    cycle_results.append(sig)
                    price = sig["close"]
                    if symbol not in active_positions:
                        if sig["buy"]:
                            execute_crypto_order(symbol, "BUY", price, sig.get("reason", "Cruce Alcista EMA"))
                        elif sig["sell"]:
                            execute_crypto_order(symbol, "SELL", price, sig.get("reason", "Cruce Bajista EMA"))
                    else:
                        pos = active_positions[symbol]
                        if pos["side"] == "BUY":
                            if price <= pos["sl"]:
                                pnl = (price - pos["entry"]) * pos["amount"]
                                send_telegram(
                                    f"🛑 *SEÑAL DE SALIDA: STOP LOSS EJECUTADO*\n\n"
                                    f"• Par: *{symbol}* [LONG]\n"
                                    f"• Entrada: *{pos['entry']:,.4f} USDT*\n"
                                    f"• Salida (SL): *{price:,.4f} USDT*\n"
                                    f"• Resultado (PnL): *{pnl:,.2f} USDT*"
                                )
                                close_paper_position(symbol, price, pnl)
                                active_positions.pop(symbol, None)
                            elif price >= pos["tp"]:
                                pnl = (price - pos["entry"]) * pos["amount"]
                                send_telegram(
                                    f"🎯 *SEÑAL DE SALIDA: TAKE PROFIT ALCANZADO*\n\n"
                                    f"• Par: *{symbol}* [LONG]\n"
                                    f"• Entrada: *{pos['entry']:,.4f} USDT*\n"
                                    f"• Salida (TP): *{price:,.4f} USDT*\n"
                                    f"• Ganancia Neta (PnL): *+{pnl:,.2f} USDT* 💰"
                                )
                                close_paper_position(symbol, price, pnl)
                                active_positions.pop(symbol, None)
                        elif pos["side"] == "SELL":
                            if price >= pos["sl"]:
                                pnl = (pos["entry"] - price) * pos["amount"]
                                send_telegram(
                                    f"🛑 *SEÑAL DE SALIDA: STOP LOSS EJECUTADO*\n\n"
                                    f"• Par: *{symbol}* [SHORT]\n"
                                    f"• Entrada: *{pos['entry']:,.4f} USDT*\n"
                                    f"• Salida (SL): *{price:,.4f} USDT*\n"
                                    f"• Resultado (PnL): *{pnl:,.2f} USDT*"
                                )
                                close_paper_position(symbol, price, pnl)
                                active_positions.pop(symbol, None)
                            elif price <= pos["tp"]:
                                pnl = (pos["entry"] - price) * pos["amount"]
                                send_telegram(
                                    f"🎯 *SEÑAL DE SALIDA: TAKE PROFIT ALCANZADO*\n\n"
                                    f"• Par: *{symbol}* [SHORT]\n"
                                    f"• Entrada: *{pos['entry']:,.4f} USDT*\n"
                                    f"• Salida (TP): *{price:,.4f} USDT*\n"
                                    f"• Ganancia Neta (PnL): *+{pnl:,.2f} USDT* 💰"
                                )
                                close_paper_position(symbol, price, pnl)
                                active_positions.pop(symbol, None)

                cycle_counter += 1
                if (cycle_counter == 1 or cycle_counter % 40 == 0) and cycle_results:
                    send_market_radar_pulse(cycle_results[:8])

            time.sleep(15)
        except KeyboardInterrupt:
            logging.info("Bot detenido por el usuario.")
            break
        except Exception as exc:
            logging.error(f"Error en loop principal: {exc}")
            time.sleep(10)


if __name__ == "__main__":
    run_crypto_loop()
