import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import TelegramBot from 'node-telegram-bot-api';

const app = express();
const port = Number(process.env.PORT || 10000);
const here = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.join(here, 'public');

app.disable('x-powered-by');
app.use(express.static(publicDir, { index: 'index.html', maxAge: '1h' }));
app.get('/healthz', (_req, res) => res.status(200).type('text/plain').send('ok'));

const token = (process.env.TELEGRAM_BOT_TOKEN || '').trim();
const appUrl = (process.env.APP_URL || process.env.RENDER_EXTERNAL_URL || '').trim();
const subscribers = new Set();
const lastAlertedCandle = new Map();
const PAIRS = [
  { symbol: 'BTC/USD', krakenPair: 'XBTUSD' },
  { symbol: 'ETH/USD', krakenPair: 'ETHUSD' },
  { symbol: 'SOL/USD', krakenPair: 'SOLUSD' },
];
const INTERVAL_MINUTES = 5;
let scanRunning = false;

function ema(values, period) {
  const alpha = 2 / (period + 1);
  let value = values[0];
  const out = [value];
  for (let i = 1; i < values.length; i += 1) {
    value = values[i] * alpha + value * (1 - alpha);
    out.push(value);
  }
  return out;
}

function rsiSeries(closes, period = 14) {
  const out = Array(closes.length).fill(null);
  for (let i = period; i < closes.length; i += 1) {
    let gains = 0;
    let losses = 0;
    for (let j = i - period + 1; j <= i; j += 1) {
      const delta = closes[j] - closes[j - 1];
      if (delta > 0) gains += delta;
      else losses -= delta;
    }
    if (losses === 0) out[i] = gains === 0 ? 50 : 100;
    else {
      const rs = (gains / period) / (losses / period);
      out[i] = 100 - 100 / (1 + rs);
    }
  }
  return out;
}

async function getMarketSignal(pair) {
  const url = new URL('https://api.kraken.com/0/public/OHLC');
  url.searchParams.set('pair', pair.krakenPair);
  url.searchParams.set('interval', String(INTERVAL_MINUTES));
  const response = await fetch(url, { signal: AbortSignal.timeout(10000) });
  if (!response.ok) throw new Error(`Kraken HTTP ${response.status}`);
  const payload = await response.json();
  if (payload.error?.length) throw new Error(payload.error.join(', '));
  const result = payload.result || {};
  const key = Object.keys(result).find((candidate) => candidate !== 'last');
  if (!key || !Array.isArray(result[key])) throw new Error(`Sin velas para ${pair.symbol}`);

  // Kraken's last OHLC row is the still-forming candle. Ignore it to avoid
  // generating a signal from a candle that may change before close.
  const candles = result[key].slice(0, -1);
  if (candles.length < 55) throw new Error(`Historial insuficiente para ${pair.symbol}`);
  const closes = candles.map((candle) => Number(candle[4]));
  if (closes.some((price) => !Number.isFinite(price) || price <= 0)) throw new Error(`Precio inválido para ${pair.symbol}`);

  const fast = ema(closes, 20);
  const slow = ema(closes, 50);
  const rsi = rsiSeries(closes, 14);
  const i = closes.length - 1;
  const p = i - 1;
  const crossUp = fast[p] <= slow[p] && fast[i] > slow[i];
  const crossDown = fast[p] >= slow[p] && fast[i] < slow[i];
  const reboundBuy = rsi[p] !== null && rsi[i] !== null && rsi[p] < 35 && rsi[i] >= 35;
  const reboundSell = rsi[p] !== null && rsi[i] !== null && rsi[p] > 65 && rsi[i] <= 65;
  const side = crossUp || reboundBuy ? 'COMPRA' : crossDown || reboundSell ? 'VENTA' : null;
  const reason = crossUp ? 'cruce alcista EMA 20/50' : crossDown ? 'cruce bajista EMA 20/50' : reboundBuy ? 'RSI sale de sobreventa' : reboundSell ? 'RSI sale de sobrecompra' : null;

  return {
    symbol: pair.symbol,
    price: closes[i],
    rsi: rsi[i],
    side,
    reason,
    candleTime: Number(candles[i][0]),
  };
}

function formatPrice(value) {
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(value);
}

async function signalMessage() {
  const results = await Promise.all(PAIRS.map(async (pair) => {
    try { return await getMarketSignal(pair); }
    catch (error) {
      console.error(`Error señal ${pair.symbol}:`, error.message);
      return { symbol: pair.symbol, error: error.message };
    }
  }));
  const lines = ['📊 Señales técnicas (Kraken, velas cerradas de 5 min):'];
  for (const item of results) {
    if (item.error) lines.push(`• ${item.symbol}: datos no disponibles`);
    else if (item.side) lines.push(`• ${item.symbol}: ${item.side} técnica a $${formatPrice(item.price)} — ${item.reason}; RSI ${item.rsi.toFixed(1)}`);
    else lines.push(`• ${item.symbol}: sin señal confirmada; $${formatPrice(item.price)}, RSI ${item.rsi.toFixed(1)}`);
  }
  lines.push('', 'Solo información técnica; no es una recomendación ni ejecuta operaciones.');
  return { text: lines.join('\n'), results };
}

async function radarMessage() {
  const results = await Promise.all(PAIRS.map(async (pair) => {
    try { return await getMarketSignal(pair); }
    catch (error) {
      console.error(`Error radar ${pair.symbol}:`, error.message);
      return { symbol: pair.symbol, error: error.message };
    }
  }));
  const lines = ['📡 Radar Kraken · USD · velas cerradas de 5 min:'];
  for (const item of results) {
    lines.push(item.error
      ? `• ${item.symbol}: no se pudieron obtener datos`
      : `• ${item.symbol}: $${formatPrice(item.price)} · RSI ${item.rsi.toFixed(1)}${item.side ? ` · ${item.side}` : ''}`);
  }
  return lines.join('\n');
}

function menuKeyboard() {
  const rows = [];
  if (appUrl.startsWith('https://')) {
    rows.push([{ text: '👻 Abrir Phantom dApp', web_app: { url: appUrl } }]);
  }
  rows.push([{ text: '📊 Señal ahora', callback_data: 'signal' }, { text: '📡 Radar', callback_data: 'radar' }]);
  rows.push([{ text: '🔔 Activar alertas', callback_data: 'alerts_on' }, { text: '🔕 Desactivar alertas', callback_data: 'alerts_off' }]);
  return { inline_keyboard: rows };
}

if (token) {
  const bot = new TelegramBot(token, { polling: true });
  bot.on('polling_error', (error) => {
    console.error('Telegram polling error:', error.message);
    if (error.message?.includes('409')) {
      console.error('Conflicto 409: otra instancia está usando polling con el mismo token. Deja un solo bot activo.');
    }
  });

  bot.onText(/^\/(start|menu|help)(?:@\w+)?(?:\s|$)/, async (message) => {
    const text = [
      'Bot de señales técnicas y acceso a la Mini App.',
      '',
      '• /signal — señal técnica actual',
      '• /radar — precios y RSI',
      '• /alerts_on — recibir avisos de señales cada 5 minutos',
      '• /alerts_off — parar avisos',
      '',
      'El bot no opera ni custodia fondos. Toda transacción en Phantom requiere tu firma.',
    ].join('\n');
    try { await bot.sendMessage(message.chat.id, text, { reply_markup: menuKeyboard() }); }
    catch (error) { console.error('Error enviando menú:', error.message); }
  });

  bot.onText(/^\/signal(?:@\w+)?(?:\s|$)/, async (message) => {
    try {
      const result = await signalMessage();
      await bot.sendMessage(message.chat.id, result.text, { reply_markup: menuKeyboard() });
    } catch (error) {
      console.error('Error /signal:', error);
      await bot.sendMessage(message.chat.id, 'No se pudo consultar el mercado ahora. Inténtalo de nuevo en unos minutos.');
    }
  });

  bot.onText(/^\/radar(?:@\w+)?(?:\s|$)/, async (message) => {
    try { await bot.sendMessage(message.chat.id, await radarMessage(), { reply_markup: menuKeyboard() }); }
    catch (error) {
      console.error('Error /radar:', error);
      await bot.sendMessage(message.chat.id, 'No se pudo consultar el radar ahora. Inténtalo de nuevo en unos minutos.');
    }
  });

  bot.onText(/^\/alerts_on(?:@\w+)?(?:\s|$)/, async (message) => {
    subscribers.add(String(message.chat.id));
    await bot.sendMessage(message.chat.id, '🔔 Alertas activadas. Revisaré BTC/USD, ETH/USD y SOL/USD cada 5 minutos mientras el servicio esté activo. Puedes cancelarlas con /alerts_off.', { reply_markup: menuKeyboard() });
  });

  bot.onText(/^\/alerts_off(?:@\w+)?(?:\s|$)/, async (message) => {
    subscribers.delete(String(message.chat.id));
    await bot.sendMessage(message.chat.id, '🔕 Alertas desactivadas.', { reply_markup: menuKeyboard() });
  });

  bot.on('callback_query', async (query) => {
    const chatId = query.message?.chat?.id;
    const data = query.data;
    try {
      await bot.answerCallbackQuery(query.id);
      if (!chatId) return;
      if (data === 'signal') {
        const result = await signalMessage();
        await bot.sendMessage(chatId, result.text, { reply_markup: menuKeyboard() });
      } else if (data === 'radar') {
        await bot.sendMessage(chatId, await radarMessage(), { reply_markup: menuKeyboard() });
      } else if (data === 'alerts_on') {
        subscribers.add(String(chatId));
        await bot.sendMessage(chatId, '🔔 Alertas activadas para señales técnicas nuevas. Se desactivan al reiniciar el servicio; puedes reactivarlas con /alerts_on.', { reply_markup: menuKeyboard() });
      } else if (data === 'alerts_off') {
        subscribers.delete(String(chatId));
        await bot.sendMessage(chatId, '🔕 Alertas desactivadas.', { reply_markup: menuKeyboard() });
      }
    } catch (error) {
      console.error('Error callback Telegram:', error.message);
      if (chatId) await bot.sendMessage(chatId, 'No se pudo completar esa acción. Inténtalo de nuevo.').catch(() => {});
    }
  });

  bot.setMyCommands([
    { command: 'start', description: 'Abrir menú' },
    { command: 'signal', description: 'Consultar señal técnica actual' },
    { command: 'radar', description: 'Consultar precios y RSI' },
    { command: 'alerts_on', description: 'Activar alertas cada 5 minutos' },
    { command: 'alerts_off', description: 'Desactivar alertas' },
  ]).catch((error) => console.error('No se pudieron registrar comandos:', error.message));

  console.log(`Bot de Telegram iniciado${appUrl ? `; Mini App: ${appUrl}` : ''}`);

  // Signal notifications are opt-in. The free Render service may sleep, so
  // alerts run only while this process is awake and subscriptions are in memory.
  setInterval(async () => {
    if (scanRunning || subscribers.size === 0) return;
    scanRunning = true;
    try {
      const results = await Promise.all(PAIRS.map(async (pair) => {
        try { return await getMarketSignal(pair); }
        catch (error) {
          console.error(`Auto-scan ${pair.symbol}:`, error.message);
          return null;
        }
      }));
      for (const item of results) {
        if (!item?.side) continue;
        const key = `${item.symbol}:${item.side}`;
        if (lastAlertedCandle.get(key) === item.candleTime) continue;
        lastAlertedCandle.set(key, item.candleTime);
        const text = `🔔 Señal técnica nueva\n${item.symbol}: ${item.side} a $${formatPrice(item.price)}\n${item.reason}; RSI ${item.rsi.toFixed(1)}.\nNo es asesoramiento financiero y no ejecuta operaciones.`;
        for (const chatId of subscribers) {
          try { await bot.sendMessage(chatId, text); }
          catch (error) { console.error(`No se pudo enviar alerta a ${chatId}:`, error.message); }
        }
      }
    } finally {
      scanRunning = false;
    }
  }, 5 * 60 * 1000);
} else {
  console.warn('TELEGRAM_BOT_TOKEN no configurado; los comandos y alertas de Telegram están desactivados.');
}

app.listen(port, '0.0.0.0', () => console.log(`Servidor web escuchando en el puerto ${port}`));
