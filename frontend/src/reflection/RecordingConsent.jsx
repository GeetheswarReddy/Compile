import React from 'react';

/** Explicit first-use consent, also reusable before a confirmed replacement. */
export default function RecordingConsent({ open = false, replacing = false, onConfirm, onCancel }) {
  if (!open) return null;

  return (
    <div className="reflection-consent" role="dialog" aria-modal="true" aria-labelledby="reflection-consent-title">
      <div className="reflection-consent__panel">
        <p className="reflection-eyebrow">Private reflection</p>
        <h2 id="reflection-consent-title">{replacing ? 'Replace your reflection?' : 'Before you record'}</h2>
        <p>
          {replacing
            ? 'Your existing reflection will be deleted before this new recording is saved.'
            : 'This audio is private to this learner and question. It is automatically deleted after 30 days, and you can delete it sooner.'}
        </p>
        <p className="reflection-consent__strong">
          {replacing ? 'Confirm replacement to continue.' : 'Do you consent to recording and storing this reflection?'}
        </p>
        <div className="reflection-actions">
          <button className="reflection-button reflection-button--primary" type="button" onClick={onConfirm}>
            {replacing ? 'Confirm replacement' : 'I consent, start recording'}
          </button>
          <button className="reflection-button reflection-button--secondary" type="button" onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
