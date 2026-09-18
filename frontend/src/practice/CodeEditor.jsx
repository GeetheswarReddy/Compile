import React from 'react';

/**
 * Small controlled Python editor used by PracticeScreen.
 * Keeping this component controlled makes unsaved learner work explicit and
 * prevents a read-only quota state from hiding the question or starter code.
 */
export default function CodeEditor({ value, onChange, readOnly = false, disabled = false }) {
  return (
    <label className="practice-editor">
      <span className="practice-editor__label">Your Python solution</span>
      <textarea
        aria-label="Your Python solution"
        className="practice-editor__input"
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
        readOnly={readOnly}
        disabled={disabled}
        spellCheck="false"
        autoCapitalize="none"
        autoCorrect="off"
      />
      {readOnly && <span className="practice-editor__note">Editing is disabled after your learner quota is used.</span>}
    </label>
  );
}
