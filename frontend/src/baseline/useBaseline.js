import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '../api/client';
import { getLearnerId } from '../identity/learnerId';

const DEFAULT_TOTAL = 5;

function progressFrom(payload) {
  const progress = payload?.progress || {};
  const answered = Number(progress.answered);
  const total = Number(progress.total);
  return {
    answered: Number.isFinite(answered) ? Math.max(0, answered) : 0,
    total: Number.isFinite(total) && total > 0 ? total : DEFAULT_TOTAL,
  };
}

/** Loads and submits the server-owned baseline resume point for this learner. */
export function useBaseline() {
  const [question, setQuestion] = useState(null);
  const [answered, setAnswered] = useState(0);
  const [total, setTotal] = useState(DEFAULT_TOTAL);
  const [completed, setCompleted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);

    try {
      getLearnerId();
      const payload = await apiClient.getBaselineNext({ signal: controller.signal });
      const progress = progressFrom(payload);
      setQuestion(payload?.question || null);
      setAnswered(Math.min(progress.answered, progress.total));
      setTotal(progress.total);
      setCompleted(Boolean(payload?.completed));
    } catch (requestError) {
      if (requestError.name !== 'AbortError') setError(requestError);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    return () => abortRef.current?.abort();
  }, [load]);

  const submit = useCallback(async (code) => {
    if (!question || submitting) return;
    setSubmitting(true);
    setError(null);

    try {
      const payload = await apiClient.submitBaseline({ questionId: question.questionId, code });
      const progress = progressFrom(payload);
      setQuestion(payload?.question || null);
      setAnswered(Math.min(progress.answered, progress.total));
      setTotal(progress.total);
      setCompleted(Boolean(payload?.completed));
      return payload;
    } catch (requestError) {
      setError(requestError);
      throw requestError;
    } finally {
      setSubmitting(false);
    }
  }, [question, submitting]);

  return { question, answered, total, completed, loading, submitting, error, retry: load, submit };
}
