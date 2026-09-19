import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import ReflectionCard from './ReflectionCard';

export default function PracticeHistory({ topicId, refreshKey }) {
  const [entries, setEntries] = useState([]);
  const [expanded, setExpanded] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    apiClient.getHistory(topicId, { signal: controller.signal })
      .then((payload) => { setEntries(payload.entries || []); setError(''); })
      .catch((error) => { if (error.name !== 'AbortError') setError(error.message); });
    return () => controller.abort();
  }, [topicId, refreshKey]);
  if (!entries.length && !error) return null;
  return <section className="practice-history" aria-label="Previous questions and reflections">
    <h2>Your previous questions</h2>
    <p>Revisit a question and play or update its reflection.</p>
    {error && <p role="alert">{error}</p>}
    {entries.map(({ question, passed }) => <article key={question.questionId}>
      <button type="button" aria-expanded={expanded === question.questionId}
        onClick={() => setExpanded(expanded === question.questionId ? '' : question.questionId)}>
        {passed ? 'Passed' : 'Practiced'} · {question.prompt}
      </button>
      {expanded === question.questionId && <ReflectionCard questionId={question.questionId} />}
    </article>)}
  </section>;
}
