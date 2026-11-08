import React from 'react';
import { createRoot } from 'react-dom/client';
import { ConnectionProvider, WalletProvider } from '@solana/wallet-adapter-react';
import { WalletModalProvider } from '@solana/wallet-adapter-react-ui';
import { PhantomWalletAdapter } from '@solana/wallet-adapter-phantom';
import App from './App.jsx';
import './index.css';
import '@solana/wallet-adapter-react-ui/styles.css';

const endpoint = import.meta.env.VITE_SOLANA_RPC_URL || 'https://api.devnet.solana.com';
const wallets = [new PhantomWalletAdapter()];

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConnectionProvider endpoint={endpoint}>
      <WalletProvider wallets={wallets} autoConnect={false}>
        <WalletModalProvider>
          <App />
        </WalletModalProvider>
      </WalletProvider>
    </ConnectionProvider>
  </React.StrictMode>,
);
