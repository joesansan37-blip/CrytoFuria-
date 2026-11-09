import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import TelegramBot from 'node-telegram-bot-api';
import { formatSignalPrice, getStrategySignals, signalReport } from './strategy.js';

const app = express();
const port = Number(process.env.PORT || 10000);
const here = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.join(here, 'public');

app.disable('x-powered-by');
app.use(express.static(publicDir, { index: 'index.html', maxAge: '1h' }));
app.get('/healthz', (_req, res) => res.status(200).type('text/plain').send('ok'));
app.get('/api/signals', async (_req, res) => {
  try {
    res.set('Cache-Control', 'no-store');
    res.json({ strategy: 'RangeBreakout_Crypto_4H', generatedAt: new Date().toISOString(), signals: await getStrategySignals() });
  } catch (error) {
    console.error('Error en /api/signals:', error);
    res.status(503).json({ error: 'No se pudieron consultar las señales ahora.' });
  }
});

const token = (process.env.TELEGRAM_BOT_TOKEN || '').trim();
const appUrl = (process.env.APP_URL || process.env.RENDER_EXTERNAL_URL || '').trim();
const subscribers = new Set();
const lastAlertedCycle = new Map();
let scanRunning = false;

function menuKeyboard() {
  const rows = [];
  if (appUrl.startsWith('https://')) rows.push([{ text: '👻 Abrir Phantom dApp', web_app: { url: appUrl } }]);
  rows.push([{ text: '📊 Señales Range Breakout', callback_data: 'signals' }, { text: '🔄 Actualizar', callback_data: 'signals' }]);
  rows.push([{ text: '🔔 Activar alertas', callback_data: 'alerts_on' }, { text: '🔕 Desactivar alertas', callback_data: 'alerts_off' }]);
  return { inline_keyboard: rows };
}

if (token) {
  const bot = new TelegramBot(token, { polling: true });
  bot.on('polling_error', (error) => {
    console.error('Telegram polling error:', error.message);
    if (error.message?.includes('409')) console.error('Conflicto 409: otra instancia usa este token. Mantén un solo proceso de polling activo.');
  });

  const replyWithSignals = async (chatId) => {
    const signals = await getStrategySignals();
    await bot.sendMessage(chatId, signalReport(signals), { reply_markup: menuKeyboard() });
  };

  bot.onText(/^\/(start|menu|help)(?:@\w+)?(?:\s|$)/, async (message) => {
    const text = [
      'Bot de señales Range Breakout y acceso a la Mini App.',
      '',
      '• /signal — consultar señales actuales',
      '• /radar — precios y estado de filtros',
      '• /alerts_on — recibir alertas de nuevas rupturas',
      '• /alerts_off — parar alertas',
      '',
      'El bot no custodia ni ejecuta órdenes. Las operaciones DEX deben revisarse y firmarse en Phantom.',
    ].join('\n');
    try { await bot.sendMessage(message.chat.id, text, { reply_markup: menuKeyboard() }); }
    catch (error) { console.error('Error menú:', error.message); }
  });
  bot.onText(/^\/(signal|radar)(?:@\w+)?(?:\s|$)/, async (message) => {
    try { await replyWithSignals(message.chat.id); }
    catch (error) {
      console.error('Error consultando señales:', error);
      await bot.sendMessage(message.chat.id, 'No se pudieron consultar los datos de mercado. Inténtalo de nuevo más tarde.');
    }
  });
  bot.onText(/^\/alerts_on(?:@\w+)?(?:\s|$)/, async (message) => {
    subscribers.add(String(message.chat.id));
    await bot.sendMessage(message.chat.id, 'Alertas activadas para nuevas rupturas confirmadas. Comprueba /alerts_off para desactivarlas. En Render gratuito pueden pausarse si el servicio duerme.', { reply_markup: menuKeyboard() });
  });
  bot.onText(/^\/alerts_off(?:@\w+)?(?:\s|$)/, async (message) => {
    subscribers.delete(String(message.chat.id));
    await bot.sendMessage(message.chat.id, 'Alertas desactivadas.', { reply_markup: menuKeyboard() });
  });
  bot.on('callback_query', async (query) => {
    const chatId = query.message?.chat?.id;
    try {
      await bot.answerCallbackQuery(query.id);
      if (!chatId) return;
      if (query.data === 'signals') await replyWithSignals(chatId);
      else if (query.data === 'alerts_on') {
        subscribers.add(String(chatId));
        await bot.sendMessage(chatId, '🔔 Alertas activadas para nuevas rupturas. Pueden pausarse cuando Render suspenda el servicio.', { reply_markup: menuKeyboard() });
      } else if (query.data === 'alerts_off') {
        subscribers.delete(String(chatId));
        await bot.sendMessage(chatId, '🔕 Alertas desactivadas.', { reply_markup: menuKeyboard() });
      }
    } catch (error) {
      console.error('Error botón Telegram:', error.message);
      if (chatId) await bot.sendMessage(chatId, 'No se pudo completar esa acción. Inténtalo de nuevo.').catch(() => {});
    }
  });

  bot.setMyCommands([
    { command: 'start', description: 'Abrir menú' },
    { command: 'signal', description: 'Consultar señal Range Breakout' },
    { command: 'radar', description: 'Consultar estado de mercado' },
    { command: 'alerts_on', description: 'Activar alertas de señales' },
    { command: 'alerts_off', description: 'Desactivar alertas' },
  ]).catch((error) => console.error('Error registrando comandos:', error.message));

  async function scanForAlerts() {
    if (scanRunning || subscribers.size === 0) return;
    scanRunning = true;
    try {
      const signals = await getStrategySignals();
      for (const signal of signals) {
        if (!signal.side || signal.error) continue;
        const key = `${signal.symbol}:${signal.cycleId}`;
        if (lastAlertedCycle.has(key)) continue;
        lastAlertedCycle.set(key, signal.candleTime);
        const text = `🔔 Range Breakout ${signal.side}\n${signal.symbol} · entrada $${formatSignalPrice(signal.price)}\nRango 4h: $${formatSignalPrice(signal.rangeLow)}–$${formatSignalPrice(signal.rangeHigh)}\nSL indicativo $${formatSignalPrice(signal.stop)} · TP indicativo $${formatSignalPrice(signal.target)}\n${signal.reason}\nSeñal informativa: no ejecuta una operación.`;
        for (const chatId of subscribers) {
          try { await bot.sendMessage(chatId, text, { reply_markup: menuKeyboard() }); }
          catch (error) { console.error(`Error enviando alerta a ${chatId}:`, error.message); }
        }
      }
    } catch (error) {
      console.error('Error escaneando alertas:', error.message);
    } finally { scanRunning = false; }
  }
  setInterval(scanForAlerts, 60_000);
  console.log(`Telegram polling iniciado${appUrl ? `; Mini App: ${appUrl}` : ''}`);
} else {
  console.warn('TELEGRAM_BOT_TOKEN no configurado; solo se sirve la dApp y la API de señales.');
}

app.listen(port, '0.0.0.0', () => console.log(`Servidor web escuchando en el puerto ${port}`));
