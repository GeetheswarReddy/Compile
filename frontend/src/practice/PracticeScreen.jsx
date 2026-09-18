import React, { useEffect } from 'react';
import CodeEditor from './CodeEditor';
import { usePractice } from './usePractice';
import './practice.css';

const topicNames = {
  arrays: 'Arrays',
  strings: 'Strings',
  'hash-maps-two-pointers': 'Hash Maps/Two Pointers',
};

function displayTopic(topicId, question) {
  return question?.topic || topicNames[topicId] || topicId;
}

export default function PracticeScreen({ topicId, onQuestionIdChange }) {
  const practice = usePractice(topicId);
  const { question, verdict, readOnly, error, loading, submitting, generating } = practice;
  const techniqueTag = question?.techniqueTag || question?.technique;

  useEffect(() => {
    onQuestionIdChange?.(question?.questionId || '');
    return () => onQuestionIdChange?.('');
  }, [onQuestionIdChange, question?.questionId]);

  return (
    <main className="practice-screen">
      <header className="practice-header">
        <div>
          <p className="practice-eyebrow">Adaptive practice</p>
          <h1>{displayTopic(topicId, question)}</h1>
        </div>
        {question && <span className="practice-difficulty">Difficulty {question.difficulty}/10</span>}
      </header>

      {readOnly && <div className="practice-banner" role="status">Learning stays available, but Run &amp; Check and generation are read-only for this learner.</div>}
      {error && <div className="practice-error" role="alert">{error}</div>}

      {loading ? (
        <p className="practice-loading" role="status">Finding your next question…</p>
      ) : question ? (
        <section className="practice-card" aria-labelledby="practice-question-title">
          <div className="practice-question">
            <div className="practice-question__meta">
              <span>{question.provenance === 'generated' ? 'Generated for your level' : 'Curated question'}</span>
              {question.techniqueTag && practice.tagRevealed && <span>Technique: {question.techniqueTag}</span>}
            </div>
            <h2 id="practice-question-title">Solve this problem</h2>
            <p className="practice-prompt">{question.prompt}</p>
            {techniqueTag && !practice.tagRevealed && (
              <button className="practice-link" type="button" onClick={practice.revealTag}>Reveal technique tag</button>
            )}
            {techniqueTag && practice.tagRevealed && <p className="practice-tag">Technique: {techniqueTag}</p>}
          </div>

          <CodeEditor value={practice.code} onChange={practice.setCode} readOnly={readOnly} disabled={readOnly} />

          <div className="practice-actions">
            <button type="button" className="practice-primary" onClick={practice.runCheck} disabled={readOnly || submitting}>
              {submitting ? 'Checking…' : 'Run & Check'}
            </button>
            <button type="button" className="practice-secondary" onClick={practice.generate} disabled={readOnly || generating}>
              {generating ? 'Generating…' : 'Generate another'}
            </button>
          </div>

          {verdict && (
            <section className={`practice-verdict ${verdict.passed ? 'is-pass' : 'is-fail'}`} aria-live="polite">
              <h2>{verdict.passed ? 'Passed' : 'Not quite yet'}</h2>
              {!verdict.passed && verdict.failedCases.length > 0 && (
                <div>
                  <p>Here are up to two cases to help you debug:</p>
                  <ul>
                    {verdict.failedCases.map((failure, index) => (
                      <li key={`${index}-${JSON.stringify(failure.input)}`}>
                        <span>Input: <code>{JSON.stringify(failure.input)}</code></span>
                        <span>Expected: <code>{JSON.stringify(failure.expected)}</code></span>
                        <span>Actual: <code>{JSON.stringify(failure.actual)}</code></span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}
        </section>
      ) : (
        <p className="practice-empty">No question is available for this topic yet.</p>
      )}
    </main>
  );
}

export { displayTopic };
