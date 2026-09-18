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
  const { question, answered, total, completed, loading, submitting, error, retry, submit } = useBaseline();
  const [code, setCode] = useState('');

  useEffect(() => {
    setCode(question?.starterCode || '');
  }, [question?.questionId, question?.starterCode]);

  const onSubmit = async (event) => {
    event.preventDefault();
    if (!code.trim() || submitting) return;
    try {
      await submit(code);
    } catch {
      // Keep the learner's code available to retry; the hook exposes the error state.
    }
  };

  if (loading) {
    return <main className="baseline-page"><section className="baseline-card baseline-state" aria-busy="true"><p className="baseline-eyebrow">Compile baseline</p><h1>Loading your assessment…</h1></section></main>;
  }

  if (error) {
    return <main className="baseline-page"><section className="baseline-card baseline-state" role="alert"><p className="baseline-eyebrow">Compile baseline</p><h1>We couldn’t load your assessment.</h1><p>{error.message}</p><button className="baseline-button" onClick={retry}>Try again</button></section></main>;
  }

  if (completed || !question) {
    return <main className="baseline-page"><section className="baseline-card baseline-state"><p className="baseline-eyebrow">Baseline complete</p><h1>Your starting point is ready.</h1><p>We’ll use these answers to tune practice to your current level.</p></section></main>;
  }

  const current = Math.min(answered + 1, total);
  const constraints = constraintsText(question.constraints);

  return (
    <main className="baseline-page">
      <section className="baseline-card" aria-labelledby="baseline-title">
        <div className="baseline-topline"><p className="baseline-eyebrow">Compile baseline</p><span>Question {current} of {total}</span></div>
        <div className="baseline-progress" aria-label={`Question ${current} of ${total}`}>
          {Array.from({ length: total }, (_, index) => <span aria-hidden="true" className={`baseline-dot ${index < answered ? 'is-done' : ''} ${index === answered ? 'is-current' : ''}`} key={index} />)}
        </div>
        <p className="baseline-topic">{labelForTopic(question.topic)}</p>
        <div className="baseline-meta"><span>Difficulty {question.difficultyScore}/10</span>{question.techniqueTag && <span>{question.techniqueTag}</span>}</div>
        <h1 id="baseline-title">{question.prompt}</h1>
        {question.functionSignature && <pre className="baseline-signature"><code>{question.functionSignature}</code></pre>}
        {constraints && <div className="baseline-constraints"><h2>Constraints</h2><p>{constraints}</p></div>}
        <form onSubmit={onSubmit}>
          <label className="baseline-code-label" htmlFor="baseline-code">Your Python solution</label>
          <textarea id="baseline-code" className="baseline-code" value={code} onChange={(event) => setCode(event.target.value)} spellCheck="false" required />
          <button className="baseline-button" type="submit" disabled={!code.trim() || submitting}>{submitting ? 'Saving…' : current === total ? 'Finish assessment' : 'Continue'}</button>
        </form>
      </section>
    </main>
  );
}

export default BaselineAssessment;
