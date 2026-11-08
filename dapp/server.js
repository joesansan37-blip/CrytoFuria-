import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import TelegramBot from 'node-telegram-bot-api';

const app = express();
const port = Number(process.env.PORT || 10000);
const here = path.dirname(fileURLToPath(import.meta.url));
const dist = path.join(here, 'dist');

app.disable('x-powered-by');
app.use(express.static(dist, { index: false, maxAge: '1h' }));
app.get('/healthz', (_req, res) => res.status(200).send('ok'));
app.get('*', (_req, res) => res.sendFile(path.join(dist, 'index.html')));

const token = (process.env.TELEGRAM_BOT_TOKEN || '').trim();
const appUrl = (process.env.APP_URL || '').trim();

if (token) {
  if (!appUrl.startsWith('https://')) {
    throw new Error('APP_URL debe ser la URL HTTPS pública de Render para usar la Mini App.');
  }

  const bot = new TelegramBot(token, { polling: true });
  bot.onText(/^\/start(?:@\w+)?(?:\s|$)/, async (message) => {
    try {
      await bot.sendMessage(
        message.chat.id,
        'Abre la Mini App para conectar Phantom. Las transferencias siempre requieren tu confirmación en la wallet.',
        {
          reply_markup: {
            inline_keyboard: [[{ text: 'Abrir Phantom dApp', web_app: { url: appUrl } }]],
          },
        },
      );
    } catch (error) {
      console.error('No se pudo responder a /start:', error.message);
    }
  });
  bot.on('polling_error', (error) => console.error('Telegram polling:', error.message));
  console.log('Bot de Telegram iniciado (polling).');
} else {
  console.log('TELEGRAM_BOT_TOKEN no configurado; solo se servirá la Mini App.');
}

app.listen(port, '0.0.0.0', () => console.log(`Servidor web escuchando en ${port}`));
