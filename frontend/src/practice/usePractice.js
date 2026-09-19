import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../api/client';

import { unwrapQuestion, readOnlyFrom, boundedFailures, normalizeVerdict } from '../api/contracts';

export function usePractice(topicId) {
  const [question, setQuestion] = useState(null);
  const [code, setCode] = useState('');
  const [verdict, setVerdict] = useState(null);
  const [readOnly, setReadOnly] = useState(false);
  const [tagRevealed, setTagRevealed] = useState(false);
  const [loading, setLoading] = useState(Boolean(topicId));
  const [submitting, setSubmitting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');

  const loadQuestion = useCallback(async (signal) => {
    if (!topicId) return null;
    setLoading(true);
    setError('');
    setVerdict(null);
    setTagRevealed(false);
    try {
      const payload = await apiClient.getNextQuestion(topicId, { signal });
      const nextQuestion = unwrapQuestion(payload);
      setQuestion(nextQuestion);
      setCode(nextQuestion?.starterCode || '');
      setReadOnly(readOnlyFrom(payload, nextQuestion));
      return nextQuestion;
    } catch (requestError) {
      if (requestError?.name !== 'AbortError') setError(requestError?.message || 'Unable to load a question.');
      return null;
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [topicId]);

  useEffect(() => {
    const controller = new AbortController();
    loadQuestion(controller.signal);
    return () => controller.abort();
  }, [loadQuestion]);

  const runCheck = useCallback(async () => {
    if (readOnly || !question?.questionId || submitting) return null;
    setSubmitting(true);
    setError('');
    try {
      const payload = await apiClient.runCheck({ questionId: question.questionId, code });
      const nextVerdict = normalizeVerdict(payload);
      setVerdict(nextVerdict);
      if (readOnlyFrom(payload, question)) setReadOnly(true);
      return nextVerdict;
    } catch (requestError) {
      if (requestError.status === 429) setReadOnly(true);
      setError(requestError?.message || 'Run & Check could not be completed.');
      return null;
    } finally {
      setSubmitting(false);
    }
  }, [code, question, readOnly, submitting]);

  const generate = useCallback(async () => {
    if (readOnly || generating || !topicId) return null;
    setGenerating(true);
    setError('');
    setVerdict(null);
    try {
      await apiClient.generate({ topicId });
      // The worker continues after this bounded browser wait. Late results are
      // offered on the next question request if still near current mastery.
      await new Promise((resolve) => setTimeout(resolve, 8000));
      const payload = await apiClient.getNextQuestion(topicId);
      const nextQuestion = unwrapQuestion(payload);
      if (nextQuestion) {
        setQuestion(nextQuestion);
        setCode(nextQuestion.starterCode || '');
        setTagRevealed(false);
      }
      setReadOnly(readOnlyFrom(payload, nextQuestion) || readOnly);
      return nextQuestion;
    } catch (requestError) {
      if (requestError.status === 429) setReadOnly(true);
      setError(requestError?.message || 'Question generation could not be completed.');
      return null;
    } finally {
      setGenerating(false);
    }
  }, [generating, readOnly, topicId]);

  return useMemo(() => ({
    question,
    code,
    setCode,
    verdict,
    readOnly,
    loading,
    submitting,
    generating,
    error,
    tagRevealed,
    revealTag: () => setTagRevealed(true),
    runCheck,
    generate,
    loadQuestion: () => loadQuestion(),
  }), [code, error, generate, generating, loadQuestion, loading, question, readOnly, runCheck, submitting, tagRevealed, verdict]);
}

export { boundedFailures, normalizeVerdict, unwrapQuestion };
