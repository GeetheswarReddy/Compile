import React from 'react';
import { useDemoTrace } from './useDemoTrace';
import './trace.css';

function formatTimestamp(timestamp) {
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? timestamp : date.toLocaleString();
}

function formatConfidence(confidence) {
  const value = Number(confidence);
  return Number.isFinite(value) ? `${Math.round(value * 100)}%` : '—';
}

export function DemoTrace({ enabled }) {
  const isEnabled = Boolean(enabled);
  const { entries, loading, error } = useDemoTrace(isEnabled);

  if (!isEnabled) return null;

  return (
    <aside className="demo-trace" aria-label="Demo trace">
      <div className="demo-trace__heading">
        <div>
          <p className="demo-trace__eyebrow">Demo mode</p>
          <h2>Demo Trace</h2>
        </div>
        <span className="demo-trace__badge">Preview</span>
      </div>

      {loading && <p className="demo-trace__status" role="status">Loading demo details…</p>}
      {error && <p className="demo-trace__status demo-trace__status--error" role="alert">Could not load demo details.</p>}
      {!loading && !error && entries.length === 0 && (
        <p className="demo-trace__status">No demo details yet.</p>
      )}

      {!loading && !error && entries.length > 0 && (
        <ol className="demo-trace__list">
          {entries.map((entry, index) => {
            const snapshot = entry.masterySnapshot || {};
            return (
              <li className="demo-trace__item" key={`${entry.eventTimestamp}-${index}`}>
                <div className="demo-trace__item-header">
                  <strong>{snapshot.topic}</strong>
                  <time dateTime={entry.eventTimestamp}>{formatTimestamp(entry.eventTimestamp)}</time>
                </div>
                <dl className="demo-trace__details">
                  <div>
                    <dt>Provenance</dt>
                    <dd>{entry.provenance}</dd>
                  </div>
                  <div>
                    <dt>Verification retries</dt>
                    <dd>{entry.verificationRetries}</dd>
                  </div>
                  <div>
                    <dt>Mastery snapshot</dt>
                    <dd>{snapshot.score ?? snapshot.mastery ?? "—"}/10</dd>
                  </div>
                  <div>
                    <dt>Confidence</dt>
                    <dd>{formatConfidence(snapshot.confidence)}</dd>
                  </div>
                </dl>
              </li>
            );
          })}
        </ol>
      )}
    </aside>
  );
}

export default DemoTrace;
