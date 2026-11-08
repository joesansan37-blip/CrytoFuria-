# Phantom Mini App para Telegram y Render

Starter de Mini App web para abrir desde un bot de Telegram. Conecta Phantom, consulta el saldo SOL, muestra la dirección pública para recibir SOL y permite enviar SOL **solo después de que Phantom presente la transacción y el usuario la firme**. El modo predeterminado es Solana devnet.

## Seguridad y alcance

- La aplicación nunca solicita ni almacena frase semilla o clave privada.
- No es custodial: “Recibir” muestra la dirección de la wallet conectada; los fondos permanecen en esa wallet.
- El envío requiere revisión y firma explícita en Phantom. No existe aprobación automática.
- Esta primera versión implementa SOL en devnet; no incluye swaps ni transferencias SPL de USDC/USDT. No uses mints inventados ni direcciones de depósito copiadas de ejemplos.
- Devnet no es dinero real. No cambies a mainnet ni uses fondos reales sin pruebas, revisión de seguridad y un RPC adecuado.

## Desarrollo local

Requiere Node.js 20 o posterior.

```bash
cd dapp
npm install
npm run dev
```

Para probar la conexión de Phantom en un navegador, abre la URL que muestra Vite. Devnet necesita SOL de prueba. El servidor de Telegram no es necesario para ejecutar el frontend localmente.

Para probar el servidor web compilado:

```bash
npm run build
npm start
```

## Despliegue en Render

El archivo `render.yaml` configura un Web Service Node con `dapp/` como raíz.

1. En Render, crea un **Blueprint** desde este repositorio y selecciona la rama `feature/phantom-solana-dapp`, o crea un Web Service con `Root Directory: dapp`, Build Command `npm install && npm run build` y Start Command `npm start`.
2. Mantén `VITE_SOLANA_RPC_URL=https://api.devnet.solana.com` y `VITE_SOLANA_NETWORK=devnet` para las primeras pruebas. Las variables `VITE_*` se incorporan al frontend durante el build; no pongas secretos en ellas.
3. Cuando Render asigne la URL HTTPS del servicio, configura `APP_URL` con esa URL completa, por ejemplo `https://nombre-del-servicio.onrender.com`.
4. Crea un bot con BotFather y configura `TELEGRAM_BOT_TOKEN` como variable secreta de Render. Nunca lo pongas en código del frontend.
5. En BotFather registra el dominio HTTPS de Render para la Mini App con `/setdomain`. Luego abre `/start` en el chat privado del bot y pulsa **Abrir Phantom dApp**.
6. Comprueba `/healthz`; debe responder `ok`.

Si no se configura `TELEGRAM_BOT_TOKEN`, Render sirve la Mini App pero no inicia el bot. Para Phantom en móvil, si el navegador interno de Telegram no abre la wallet, abre la Mini App en un navegador compatible con Phantom.

## Advertencias antes de producción

El endpoint público de devnet es solo para pruebas y puede tener límites. Para producción se requiere un RPC fiable, cambiar explícitamente a mainnet y probar primero con cantidades pequeñas. Una dirección pública permite recibir SOL, pero no da a la dApp autoridad para retirar los fondos de esa wallet.
