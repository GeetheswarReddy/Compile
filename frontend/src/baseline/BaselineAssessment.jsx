import QuestionExamples from '../practice/QuestionExamples';
import React, { useEffect, useState } from 'react';
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
    question, answered, total, completed, loading, submitting, error,
    errorOperation, quotaExhausted, retry, submit,
  } = useBaseline();
  const [code, setCode] = useState('');

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
    return <main className="baseline-page"><section className="baseline-card baseline-state"><p className="baseline-eyebrow">Baseline complete</p><h1>Your starting point is ready.</h1><p>We’ll use these answers to tune practice to your current level.</p><a className="baseline-button" href="/">Choose a practice topic</a></section></main>;
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
        <div className="baseline-workspace">
          <section className="baseline-question-pane" aria-labelledby="baseline-title">
            <p className="baseline-topic">{labelForTopic(question.topic)}</p>
            <div className="baseline-meta"><span>Difficulty {question.difficulty}/10</span></div>
            <h1 id="baseline-title">{question.prompt}</h1>
            <QuestionExamples examples={question.examples} />
            {question.functionSignature && <pre className="baseline-signature"><code>{question.functionSignature}</code></pre>}
            {constraints && <div className="baseline-constraints"><h2>Constraints</h2><p>{constraints}</p></div>}
          </section>
          <form className="baseline-solution-pane" onSubmit={onSubmit}>
            <label className="baseline-code-label" htmlFor="baseline-code">Your Python solution</label>
            <textarea id="baseline-code" className="baseline-code" value={code} onChange={(event) => setCode(event.target.value)} spellCheck="false" required />
            {error && errorOperation === 'submit' && (
              <div className="baseline-submit-error" role="alert">
                <p>{quotaExhausted ? 'The demo execution quota is exhausted. Your answer is still here, but it cannot be checked right now.' : error.message}</p>
                {!quotaExhausted && <p>Your solution and assessment position were kept. Submit again when you’re ready.</p>}
              </div>
            )}
            <button className="baseline-button" type="submit" disabled={!code.trim() || submitting || quotaExhausted}>{submitting ? 'Checking…' : current === total ? 'Finish assessment' : 'Continue'}</button>
          </form>
        </div>
      </section>
    </main>
  );
}

export default BaselineAssessment;
