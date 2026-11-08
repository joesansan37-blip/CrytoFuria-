import { useCallback, useEffect, useState } from 'react';
import { LAMPORTS_PER_SOL, PublicKey, SystemProgram, Transaction } from '@solana/web3.js';
import { useConnection, useWallet } from '@solana/wallet-adapter-react';
import { WalletMultiButton } from '@solana/wallet-adapter-react-ui';

const NETWORK = import.meta.env.VITE_SOLANA_NETWORK || 'devnet';
const LAMPORTS_RESERVE = 10_000; // Keep a small amount for network fees.

function shortAddress(address) {
  return address ? `${address.slice(0, 5)}…${address.slice(-5)}` : '';
}

export default function App() {
  const { connection } = useConnection();
  const { publicKey, connected, sendTransaction } = useWallet();
  const [balance, setBalance] = useState(null);
  const [recipient, setRecipient] = useState('');
  const [amount, setAmount] = useState('0.01');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  const refreshBalance = useCallback(async () => {
    if (!publicKey) {
      setBalance(null);
      return;
    }
    try {
      const lamports = await connection.getBalance(publicKey, 'confirmed');
      setBalance(lamports / LAMPORTS_PER_SOL);
    } catch (error) {
      setStatus(`No se pudo consultar el saldo: ${error.message}`);
    }
  }, [connection, publicKey]);

  useEffect(() => {
    refreshBalance();
  }, [refreshBalance]);

  const sendSol = async (event) => {
    event.preventDefault();
    setStatus('');

    if (!publicKey) return setStatus('Conecta Phantom antes de enviar.');
    const sol = Number(amount);
    if (!Number.isFinite(sol) || sol <= 0) return setStatus('Escribe una cantidad de SOL válida y mayor que cero.');

    let to;
    try {
      to = new PublicKey(recipient.trim());
    } catch {
      return setStatus('La dirección de destino no es válida.');
    }
    if (to.equals(publicKey)) return setStatus('La dirección destino es la misma wallet conectada.');

    const lamports = Math.round(sol * LAMPORTS_PER_SOL);
    if (!Number.isSafeInteger(lamports) || lamports <= 0) return setStatus('La cantidad está fuera del rango permitido.');

    setBusy(true);
    try {
      const currentLamports = await connection.getBalance(publicKey, 'confirmed');
      if (currentLamports < lamports + LAMPORTS_RESERVE) {
        throw new Error('Saldo insuficiente para el envío y las comisiones de red.');
      }

      const latest = await connection.getLatestBlockhash('confirmed');
      const transaction = new Transaction({
        feePayer: publicKey,
        recentBlockhash: latest.blockhash,
      }).add(SystemProgram.transfer({ fromPubkey: publicKey, toPubkey: to, lamports }));

      setStatus('Revisa los detalles y confirma la transacción en Phantom…');
      const signature = await sendTransaction(transaction, connection);
      await connection.confirmTransaction({ signature, ...latest }, 'confirmed');
      setStatus(`Envío confirmado: ${signature}`);
      setAmount('0.01');
      await refreshBalance();
    } catch (error) {
      setStatus(`No se completó el envío: ${error.message || 'error desconocido'}`);
    } finally {
      setBusy(false);
    }
  };

  const explorerUrl = (signature) =>
    `https://explorer.solana.com/tx/${signature}?cluster=${encodeURIComponent(NETWORK)}`;
  const signature = status.match(/Envío confirmado: ([1-9A-HJ-NP-Za-km-z]+)/)?.[1];

  return (
    <main className="page">
      <section className="card">
        <div className="brand"><span className="mark">◎</span><div><p className="eyebrow">SOLANA · {NETWORK.toUpperCase()}</p><h1>Phantom Wallet</h1></div></div>
        <p className="intro">Conecta tu wallet para consultar el saldo y enviar SOL. Phantom te mostrará cada transacción para que la revises y firmes.</p>

        <div className="wallet-row">
          <WalletMultiButton />
          {connected && publicKey && <span className="address">{shortAddress(publicKey.toBase58())}</span>}
        </div>

        {connected && publicKey ? (
          <>
            <section className="balance panel">
              <div><p className="label">Saldo de la wallet conectada</p><p className="amount">{balance === null ? '—' : balance.toLocaleString(undefined, { maximumFractionDigits: 6 })}<span> SOL</span></p></div>
              <button className="secondary" type="button" onClick={refreshBalance}>Actualizar</button>
            </section>

            <section className="panel">
              <h2>Recibir SOL</h2>
              <p className="muted">Esta es la dirección pública de tu wallet conectada. Compártela solo si deseas recibir fondos; la dApp no custodia los depósitos.</p>
              <div className="address-box">{publicKey.toBase58()}</div>
              <button className="secondary copy" type="button" onClick={() => navigator.clipboard?.writeText(publicKey.toBase58()).then(() => setStatus('Dirección copiada.')).catch(() => setStatus('No se pudo copiar; selecciona la dirección manualmente.'))}>Copiar dirección</button>
            </section>

            <form className="panel" onSubmit={sendSol}>
              <h2>Enviar SOL</h2>
              <label htmlFor="recipient">Dirección de destino</label>
              <input id="recipient" autoComplete="off" spellCheck="false" value={recipient} onChange={(event) => setRecipient(event.target.value)} placeholder="Dirección pública Solana" required />
              <label htmlFor="amount">Cantidad (SOL)</label>
              <input id="amount" type="number" min="0.000001" step="0.000001" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} required />
              <button className="primary" type="submit" disabled={busy}>{busy ? 'Esperando confirmación…' : 'Revisar y firmar en Phantom'}</button>
              <p className="fine">La transacción solo se envía tras tu aprobación en Phantom. Comprueba cuidadosamente la dirección, red y cantidad.</p>
            </form>
          </>
        ) : (
          <div className="panel empty"><h2>Conecta tu wallet</h2><p className="muted">Usa el botón de arriba para conectar Phantom. Nunca compartas tu frase secreta ni clave privada.</p></div>
        )}

        {status && <div className="status" role="status">{status}{signature && <> · <a href={explorerUrl(signature)} target="_blank" rel="noreferrer">Ver en Solana Explorer</a></>}</div>}
        <footer>Red actual: {NETWORK}. Prueba primero en devnet; los activos de devnet no tienen valor real.</footer>
      </section>
    </main>
  );
}
