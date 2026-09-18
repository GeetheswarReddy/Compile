import React from 'react';
import { createRoot } from 'react-dom/client';
import './styles/global.css';

function Foundation() {
  return (
    <main className="app-shell">
      <h1>Compile</h1>
      <p>Adaptive Python practice is loading.</p>
    </main>
  );
}

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error('Compile could not find its application root.');
}

createRoot(rootElement).render(
  <React.StrictMode>
    <Foundation />
  </React.StrictMode>,
);
