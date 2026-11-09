const PAIRS = [
  { symbol: 'BTC/USD', krakenPair: 'XBTUSD' },
  { symbol: 'ETH/USD', krakenPair: 'ETHUSD' },
  { symbol: 'SOL/USD', krakenPair: 'SOLUSD' },
];

const INTERVAL_MINUTES = 5;
const BARS_IN_RANGE = 48; // 4 hours of 5-minute candles
const MIN_RANGE_PCT = 0.15;
const MAX_RANGE_PCT = 4.0;
const MAX_SPREAD_PCT = 0.08;
const VOLUME_LOOKBACK = 20;
const VOLUME_MULTIPLIER = 1.3;
const RISK_REWARD = 1.8;

async function getKrakenJson(path, params) {
  const url = new URL(`https://api.kraken.com/0/public/${path}`);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, String(value));
  const response = await fetch(url, { signal: AbortSignal.timeout(10000) });
  if (!response.ok) throw new Error(`Kraken HTTP ${response.status}`);
  const payload = await response.json();
  if (payload.error?.length) throw new Error(payload.error.join(', '));
  return payload.result || {};
}

function marketResultKey(result) {
  return Object.keys(result).find((key) => key !== 'last');
}

async function getPairSignal(pair) {
  const [ohlc, ticker] = await Promise.all([
    getKrakenJson('OHLC', { pair: pair.krakenPair, interval: INTERVAL_MINUTES }),
    getKrakenJson('Ticker', { pair: pair.krakenPair }),
  ]);
  const candleKey = marketResultKey(ohlc);
  const tickerKey = marketResultKey(ticker);
  if (!candleKey || !tickerKey || !Array.isArray(ohlc[candleKey])) throw new Error('Datos de mercado incompletos');

  // Kraken's last row is the currently forming candle; only closed candles count.
  const closed = ohlc[candleKey].slice(0, -1);
  if (closed.length < BARS_IN_RANGE + VOLUME_LOOKBACK + 1) throw new Error('Historial insuficiente');
  const breakout = closed.at(-1);
  const rangeBars = closed.slice(-(BARS_IN_RANGE + 1), -1);
  const volumeBars = closed.slice(-(VOLUME_LOOKBACK + 1), -1);
  const high = Math.max(...rangeBars.map((bar) => Number(bar[2])));
  const low = Math.min(...rangeBars.map((bar) => Number(bar[3])));
  const close = Number(breakout[4]);
  const volume = Number(breakout[6]);
  const averageVolume = volumeBars.reduce((sum, bar) => sum + Number(bar[6]), 0) / volumeBars.length;
  const tickerData = ticker[tickerKey];
  const bid = Number(tickerData.b?.[0]);
  const ask = Number(tickerData.a?.[0]);
  const spreadPct = bid > 0 && ask >= bid ? ((ask - bid) / ((ask + bid) / 2)) * 100 : Infinity;
  const rangePct = ((high - low) / ((high + low) / 2)) * 100;
  const volumeOk = averageVolume > 0 && volume >= averageVolume * VOLUME_MULTIPLIER;
  const rangeOk = rangePct >= MIN_RANGE_PCT && rangePct <= MAX_RANGE_PCT;
  const spreadOk = spreadPct <= MAX_SPREAD_PCT;

  let side = null;
  let reason = 'Sin ruptura confirmada';
  if (rangeOk && spreadOk && volumeOk && close > high) {
    side = 'LONG';
    reason = 'Cierre por encima del máximo del rango de 4h';
  } else if (rangeOk && spreadOk && volumeOk && close < low) {
    side = 'SHORT';
    reason = 'Cierre por debajo del mínimo del rango de 4h';
  }

  const stop = side === 'LONG' ? low : side === 'SHORT' ? high : null;
  const risk = stop === null ? null : Math.abs(close - stop);
  const target = side === 'LONG' ? close + risk * RISK_REWARD : side === 'SHORT' ? close - risk * RISK_REWARD : null;
  const candleTime = Number(breakout[0]);

  return {
    symbol: pair.symbol,
    timeframe: '5m',
    rangeHours: 4,
    candleTime,
    price: close,
    rangeHigh: high,
    rangeLow: low,
    rangePct,
    spreadPct,
    volume,
    averageVolume,
    side,
    reason: side ? reason : !rangeOk ? 'Rango fuera de límites' : !spreadOk ? 'Spread excede el máximo' : !volumeOk ? 'Volumen insuficiente' : reason,
    stop,
    target,
    riskReward: RISK_REWARD,
    cycleId: Math.floor(candleTime / (4 * 60 * 60)),
  };
}

export async function getStrategySignals() {
  return Promise.all(PAIRS.map(async (pair) => {
    try {
      return await getPairSignal(pair);
    } catch (error) {
      console.error(`Error estrategia ${pair.symbol}:`, error.message);
      return { symbol: pair.symbol, timeframe: '5m', side: null, error: 'Datos temporalmente no disponibles' };
    }
  }));
}

export function formatSignalPrice(value) {
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(value);
}

export function signalReport(signals) {
  const lines = ['📊 Range Breakout · velas cerradas 5m · Kraken'];
  for (const signal of signals) {
    if (signal.error) {
      lines.push(`• ${signal.symbol}: datos no disponibles`);
    } else if (signal.side) {
      lines.push(`• ${signal.symbol}: ${signal.side} · entrada $${formatSignalPrice(signal.price)} · SL $${formatSignalPrice(signal.stop)} · TP $${formatSignalPrice(signal.target)} · ${signal.reason}`);
    } else {
      lines.push(`• ${signal.symbol}: sin entrada · $${formatSignalPrice(signal.price)} · ${signal.reason}`);
    }
  }
  lines.push('', 'Solo señales informativas; el bot no ejecuta órdenes. Verifica precio y riesgo antes de firmar cualquier operación.');
  return lines.join('\n');
}
