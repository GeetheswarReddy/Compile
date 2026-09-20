import QuestionExamples from '../practice/QuestionExamples';
import React, { useEffect } from 'react';
import CodeEditor from './CodeEditor';
import { useResizableColumns } from '../layout/useResizableColumns';
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

function constraintsText(constraints) {
  if (Array.isArray(constraints)) return constraints.join('\n');
  return constraints || '';
}

export default function PracticeScreen({
  topicId,
  onQuestionIdChange,
  onAttemptChange,
  trace = null,
  support = null,
  history = null,
}) {
  const practice = usePractice(topicId);
  const resize = useResizableColumns('compile-practice-left-pane');
  const { question, verdict, readOnly, error, loading, submitting, generating } = practice;
  const techniqueTag = question?.techniqueTag || question?.technique;
  const constraints = constraintsText(question?.constraints);

  useEffect(() => {
    onQuestionIdChange?.(question?.questionId || '');
    return () => onQuestionIdChange?.('');
  }, [onQuestionIdChange, question?.questionId]);

  useEffect(() => { onAttemptChange?.(Boolean(verdict)); }, [verdict, onAttemptChange]);

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
        <section className="practice-state" aria-busy="true">
          <p className="practice-loading" role="status">Finding your next question…</p>
        </section>
      ) : question ? (
        <section className={`practice-workspace ${trace ? 'has-trace' : ''}`} aria-label="Practice workspace" ref={resize.containerRef} style={resize.containerStyle}>
          <section className="practice-pane practice-question-pane" aria-labelledby="practice-question-title">
            <div className="practice-question">
              <div className="practice-question__meta">
                <span>{question.provenance === 'generated' ? 'Generated for your level' : 'Curated question'}</span>
                <span>Difficulty {question.difficulty}/10</span>
              </div>
              <h2 id="practice-question-title">Solve this problem</h2>
              <p className="practice-prompt">{question.prompt}</p>
              <QuestionExamples examples={question.examples} />
              {question.functionSignature && <pre className="practice-signature"><code>{question.functionSignature}</code></pre>}
              {constraints && (
                <section className="practice-constraints" aria-labelledby="practice-constraints-title">
                  <h3 id="practice-constraints-title">Constraints</h3>
                  <p>{constraints}</p>
                </section>
              )}
              {techniqueTag && !practice.tagRevealed && (
                <button className="practice-link" type="button" onClick={practice.revealTag}>Reveal technique tag</button>
              )}
              {techniqueTag && practice.tagRevealed && <p className="practice-tag">Technique: {techniqueTag}</p>}
            </div>
            {(support || history) && (
              <div className="practice-support-region">
                {support}
                {history}
              </div>
            )}
          </section>

          <div className="workspace-resizer" {...resize.separatorProps}><span aria-hidden="true" /></div>

          {trace && <div className="practice-trace-slot">{trace}</div>}

          <section className="practice-pane practice-solution-pane" aria-label="Python solution">
            <div className="practice-editor-stage">
              <CodeEditor value={practice.code} onChange={practice.setCode} readOnly={readOnly} disabled={readOnly} />
            </div>

            <div className="practice-actions" aria-label="Solution actions">
              <button type="button" className="practice-primary" onClick={practice.runCheck} disabled={readOnly || submitting || generating}>
                {submitting ? 'Checking…' : 'Run & Check'}
              </button>
              <button type="button" className="practice-secondary" onClick={practice.generate} disabled={readOnly || generating || submitting}>
                {generating ? 'Generating…' : 'Generate another'}
              </button>
              <button type="button" className="practice-secondary" onClick={practice.loadQuestion} disabled={loading || generating || submitting || !verdict}>Next question</button>
            </div>

            {!verdict && !submitting && (
              <p className="practice-check-help">Run &amp; Check executes your code against the question tests and shows whether it is correct.</p>
            )}

            {verdict && (
              <section className={`practice-verdict ${verdict.passed ? 'is-pass' : 'is-fail'}`} aria-live="polite">
                <p className="practice-verdict__label">Test result</p>
                <h2>{verdict.passed ? 'Passed — your code is correct' : 'Not quite yet — some tests failed'}</h2>
                <p className="practice-verdict__summary">
                  {verdict.passed
                    ? 'Your solution produced the expected output.'
                    : 'Update your code and use Run & Check again.'}
                </p>
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
        </section>
      ) : (
        <section className="practice-state">
          <p className="practice-empty">You’ve completed the available questions for this topic. Choose another topic to keep learning.</p>
          {history}
        </section>
      )}
    </main>
  );
}

export { displayTopic };
