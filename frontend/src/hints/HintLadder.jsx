import React, { useCallback, useState } from 'react';
import { apiClient } from '../api/client';
import '../reflection/reflection.css';

const HINT_NAMES = ['Nudge', 'Approach', 'Pseudocode', 'Reference solution'];

function hintText(payload) {
  return payload?.hint || payload?.text || payload?.content || payload?.body || '';
}

/**
 * Four-step, learner-requested hint disclosure.
 * Props: questionId (required), optional onHint(payload), disabled, className.
 */
export default function HintLadder({ questionId, onHint, disabled = false, className = '' }) {
  const [currentLevel, setCurrentLevel] = useState(0);
  const [hints, setHints] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const requestHint = useCallback(async () => {
    if (!questionId || loading || disabled || currentLevel >= HINT_NAMES.length) return;

    setLoading(true);
    setError('');
    try {
      const payload = await apiClient.getHint({ questionId, currentLevel });
      const level = Number(payload?.level || currentLevel + 1);
      const item = {
        ...payload,
        level,
        name: payload?.name || HINT_NAMES[level - 1] || `Hint ${level}`,
        text: hintText(payload),
      };
      setHints((previous) => [...previous, item]);
      setCurrentLevel(Math.max(currentLevel + 1, level));
      onHint?.(item);
    } catch (requestError) {
      setError(requestError?.message || 'This hint could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [currentLevel, disabled, loading, onHint, questionId]);

  return (
    <section className={`hint-ladder ${className}`.trim()} aria-labelledby="hint-ladder-title">
      <div className="hint-ladder__header">
        <div>
          <p className="reflection-eyebrow">Need a nudge?</p>
          <h2 id="hint-ladder-title">Hint ladder</h2>
        </div>
        <span className="hint-ladder__count">{currentLevel}/{HINT_NAMES.length} used</span>
      </div>
      <p className="hint-ladder__note">Hints are revealed one at a time and may lower mastery confidence.</p>

      <ol className="hint-ladder__steps">
        {HINT_NAMES.map((name, index) => (
          <li className={index < currentLevel ? 'is-open' : ''} key={name}>
            <span className="hint-ladder__step-number">{index + 1}</span>
            <span>{name}</span>
          </li>
        ))}
      </ol>

      {hints.length > 0 && (
        <div className="hint-ladder__answers" aria-live="polite">
          {hints.map((hint, index) => (
            <article className="hint-ladder__hint" key={`${hint.level}-${index}`}>
              <h3>{hint.name}</h3>
              <p>{hint.text || 'Hint received.'}</p>
            </article>
          ))}
        </div>
      )}

      {error && <p className="reflection-error" role="alert">{error}</p>}
      <button className="reflection-button reflection-button--secondary" type="button" onClick={requestHint} disabled={disabled || loading || !questionId || currentLevel >= HINT_NAMES.length}>
        {loading ? 'Loading hint…' : currentLevel >= HINT_NAMES.length ? 'All hints revealed' : `Reveal ${HINT_NAMES[currentLevel]}`}
      </button>
    </section>
  );
}

export { HINT_NAMES };
