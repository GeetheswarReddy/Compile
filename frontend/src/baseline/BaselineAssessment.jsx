import QuestionExamples from '../practice/QuestionExamples';
import React, { useEffect, useState } from 'react';
import CodeEditor from '../practice/CodeEditor';
import { useResizableColumns } from '../layout/useResizableColumns';
import { useBaseline } from './useBaseline';
import './baseline.css';

const TOPIC_LABELS = {
  arrays: 'Arrays',
  strings: 'Strings',
  'hash-maps-two-pointers': 'Hash Maps / Two Pointers',
};

function labelForTopic(topic) {
  return TOPIC_LABELS[String(topic || '').toLowerCase()] || topic || 'Baseline question';
}

function constraintsText(constraints) {
  if (Array.isArray(constraints)) return constraints.join('\n');
  return constraints || '';
}

export function BaselineAssessment() {
  const {
    question, answered, total, completed, loading, submitting, error, mastery,
    errorOperation, verdict, canAdvance, quotaExhausted, retry, submit, advance,
  } = useBaseline();
  const [code, setCode] = useState('');
  const resize = useResizableColumns('compile-baseline-left-pane');

  useEffect(() => {
    setCode(question?.starterCode || '');
  }, [question?.questionId, question?.starterCode]);

  const onSubmit = async (event) => {
    event.preventDefault();
    if (!code.trim() || submitting) return;
    await submit(code);
  };

  if (loading) {
    return <main className="baseline-page"><section className="baseline-card baseline-state" aria-busy="true"><p className="baseline-eyebrow">Compile baseline</p><h1>Loading your assessment…</h1></section></main>;
  }

  if (error && errorOperation === 'load') {
    return <main className="baseline-page"><section className="baseline-card baseline-state" role="alert"><p className="baseline-eyebrow">Compile baseline</p><h1>We couldn’t load your assessment.</h1><p>{error.message}</p><button className="baseline-button" onClick={retry}>Try again</button></section></main>;
  }

  if (completed) {
    return (
      <main className="baseline-page">
        <section className="baseline-card baseline-state baseline-summary" aria-labelledby="baseline-summary-title">
          <p className="baseline-eyebrow">Baseline complete · {answered}/{total}</p>
          <h1 id="baseline-summary-title">Your starting levels</h1>
          <p>These scores select the difficulty of your first practice questions.</p>
          <div className="baseline-summary__grid" aria-label="Baseline mastery by topic">
            {mastery.length > 0 ? mastery.map((item) => (
              <article key={item.topic}>
                <span>{item.topic}</span>
                <strong>{item.score}<small>/10</small></strong>
                <p>Confidence {Math.round(Number(item.confidence) * 100)}%</p>
              </article>
            )) : <p className="baseline-summary__empty">Your baseline is complete. Topic scores will appear after your next refresh.</p>}
          </div>
          <a className="baseline-button" href="/">Choose a practice topic</a>
        </section>
      </main>
    );
  }

  if (!question) return <main className="baseline-page"><p>No assessment question is available. Please retry.</p><button onClick={retry}>Retry</button></main>;

  const current = Math.min(answered + 1, total);
  const constraints = constraintsText(question.constraints);

  return (
    <main className="baseline-page">
      <section className="baseline-card" aria-labelledby="baseline-title">
        <div className="baseline-topline"><p className="baseline-eyebrow">Compile baseline</p><span>Question {current} of {total}</span></div>
        <div className="baseline-progress" aria-label={`Question ${current} of ${total}`}>
          {Array.from({ length: total }, (_, index) => <span aria-hidden="true" className={`baseline-dot ${index < answered ? 'is-done' : ''} ${index === answered ? 'is-current' : ''}`} key={index} />)}
        </div>
        <div className="baseline-workspace" ref={resize.containerRef} style={resize.containerStyle}>
          <section className="baseline-question-pane" aria-labelledby="baseline-title">
            <p className="baseline-topic">{labelForTopic(question.topic)}</p>
            <div className="baseline-meta"><span>Difficulty {question.difficulty}/10</span></div>
            <h1 id="baseline-title">{question.prompt}</h1>
            <QuestionExamples examples={question.examples} />
            {question.functionSignature && <pre className="baseline-signature"><code>{question.functionSignature}</code></pre>}
            {constraints && <div className="baseline-constraints"><h2>Constraints</h2><p>{constraints}</p></div>}
          </section>
          <div className="workspace-resizer" {...resize.separatorProps}><span aria-hidden="true" /></div>
          <form className="baseline-solution-pane" onSubmit={onSubmit}>
            <CodeEditor
              value={code}
              onChange={setCode}
              readOnly={Boolean(verdict)}
              disabled={quotaExhausted}
              readOnlyMessage="This answer has been checked. Continue when you are ready."
            />
            {error && errorOperation === 'submit' && (
              <div className="baseline-submit-error" role="alert">
                <p>{quotaExhausted ? 'The demo execution quota is exhausted. Your answer is still here, but it cannot be checked right now.' : error.message}</p>
                {!quotaExhausted && <p>Your solution and assessment position were kept. Submit again when you’re ready.</p>}
              </div>
            )}
            {verdict && (
              <section className={`baseline-verdict ${verdict.passed ? 'is-pass' : 'is-fail'}`} aria-live="polite">
                <p className="baseline-verdict__label">Test result</p>
                <h2>{verdict.passed ? 'Passed — your code is correct' : 'Not quite yet — some tests failed'}</h2>
                <p>{verdict.passed ? 'Your solution produced the expected output.' : 'Review the diagnostics, then continue to the next baseline question.'}</p>
                {!verdict.passed && verdict.failedCases.length > 0 && (
                  <ul>
                    {verdict.failedCases.map((failure, index) => (
                      <li key={`${index}-${JSON.stringify(failure.input)}`}>
                        <span>Input: <code>{JSON.stringify(failure.input)}</code></span>
                        <span>Expected: <code>{JSON.stringify(failure.expected)}</code></span>
                        <span>Actual: <code>{JSON.stringify(failure.actual)}</code></span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}
            {!verdict && <p className="baseline-check-help">Run &amp; Check evaluates this solution before the assessment advances.</p>}
            {canAdvance ? (
              <button className="baseline-button" type="button" onClick={advance}>{current === total ? 'Finish assessment' : 'Next question'}</button>
            ) : (
              <button className="baseline-button" type="submit" disabled={!code.trim() || submitting || quotaExhausted}>{submitting ? 'Checking…' : 'Run & Check'}</button>
            )}
          </form>
        </div>
      </section>
    </main>
  );
}

export default BaselineAssessment;
