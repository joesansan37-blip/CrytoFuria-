# Phantom Mini App para Telegram y Render

Versión web estática mínima para probar Phantom en Solana **devnet**. Render sirve el HTML directamente (sin React/Vite ni compilación del frontend); Telegram puede mostrar un botón `/start` que abre la Mini App.

## Funciones
- Conectar Phantom en navegadores que inyecten el proveedor Solana.
- Mostrar dirección pública y saldo SOL de devnet.
- Recibir: muestra la dirección de la wallet conectada; la app no custodia los fondos.
- Enviar SOL de devnet con revisión y firma explícita del usuario en Phantom.
- Enlace para abrir la página en el navegador de Phantom si Telegram no expone el proveedor.

No pide ni almacena claves privadas/frase semilla. No hay firma automática. No uses dinero real: esta versión fija el RPC y el explorador a devnet.

## Despliegue manual en Render
En el Web Service configura:
- Branch: `feature/phantom-solana-dapp`
- Root Directory: `dapp`
- Build Command: `npm install`
- Start Command: `npm start`
- Plan: Free, si aparece disponible en tu cuenta. El servicio gratuito puede suspenderse por inactividad.

Variables de entorno:
- `TELEGRAM_BOT_TOKEN`: opcional para servir solo la página; necesario para que el bot responda a `/start`. Créalo con BotFather y mantenlo secreto.
- `APP_URL`: opcional si `RENDER_EXTERNAL_URL` no está disponible; si se configura, usa la URL HTTPS pública del servicio. No compartas el token.
- `PORT`: Render lo proporciona automáticamente.

Comprueba `https://TU-SERVICIO.onrender.com/healthz` (debe responder `ok`) y abre la URL raíz. Para Telegram, registra el dominio HTTPS en BotFather con `/setdomain`, inicia el bot con `/start` y abre la Mini App. Solo un proceso debe hacer polling con el mismo token.

## Límites deliberados
Esta versión no implementa transferencias SPL de USDC/USDT ni swaps Jupiter. La Jupiter Swap API actual está pensada para mainnet, no devnet; inventar mints o mostrar un swap ficticio sería inseguro. Para añadir esos activos/swap hace falta decidir explícitamente una arquitectura mainnet y probar con cantidades mínimas, o crear mints propios de devnet para ensayar solo transferencias de tokens.
