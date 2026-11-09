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

if (token && appUrl.startsWith('https://')) {
  const bot = new TelegramBot(token, { polling: true });
  bot.onText(/^\/start(?:@\w+)?(?:\s|$)/, async (message) => {
    try {
      await bot.sendMessage(message.chat.id, 'Abre la Mini App para conectar Phantom. Las transferencias requieren tu confirmación en Phantom.', {
        reply_markup: {
          inline_keyboard: [[{ text: 'Abrir Phantom dApp', web_app: { url: appUrl } }]],
        },
      });
    } catch (error) {
      console.error('Error respondiendo a /start:', error.message);
    }
  });
  bot.on('polling_error', (error) => console.error('Telegram polling:', error.message));
  console.log(`Bot de Telegram activo. Mini App: ${appUrl}`);
} else if (token) {
  console.error('Bot no iniciado: configura APP_URL como URL HTTPS pública del servicio Render.');
} else {
  console.log('TELEGRAM_BOT_TOKEN no configurado; solo se sirve la página web.');
}

app.listen(port, '0.0.0.0', () => console.log(`Servidor web escuchando en el puerto ${port}`));
