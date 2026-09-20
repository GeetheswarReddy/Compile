import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '../api/client';
import { isAbortError, isQuotaError, normalizeVerdict } from '../api/contracts';
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
  const [errorOperation, setErrorOperation] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [pendingAdvance, setPendingAdvance] = useState(null);
  const abortRef = useRef(null);
  const submitAbortRef = useRef(null);
  const loadSequenceRef = useRef(0);
  const submitLockRef = useRef(false);
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    const sequence = ++loadSequenceRef.current;
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    setErrorOperation(null);
    setVerdict(null);
    setPendingAdvance(null);

    try {
      getLearnerId();
      const payload = await apiClient.getBaselineNext({ signal: controller.signal });
      if (controller.signal.aborted || sequence !== loadSequenceRef.current || !mountedRef.current) return null;
      const progress = progressFrom(payload);
      setQuestion(payload?.question || null);
      setAnswered(Math.min(progress.answered, progress.total));
      setTotal(progress.total);
      setCompleted(Boolean(payload?.completed));
      return payload;
    } catch (requestError) {
      if (!isAbortError(requestError) && sequence === loadSequenceRef.current && mountedRef.current) {
        setError(requestError);
        setErrorOperation('load');
      }
      return null;
    } finally {
      if (!controller.signal.aborted && sequence === loadSequenceRef.current && mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    load();
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      submitAbortRef.current?.abort();
    };
  }, [load]);

  const submit = useCallback(async (code) => {
    if (!question || submitLockRef.current) return null;
    submitLockRef.current = true;
    const controller = new AbortController();
    submitAbortRef.current = controller;
    setSubmitting(true);
    setError(null);
    setErrorOperation(null);

    try {
      const payload = await apiClient.submitBaseline(
        { questionId: question.questionId, code },
        { signal: controller.signal },
      );
      if (controller.signal.aborted || !mountedRef.current) return null;
      if (typeof payload?.verdict?.passed === 'boolean') {
        setVerdict(normalizeVerdict(payload.verdict));
        setPendingAdvance(payload);
      } else {
        const progress = progressFrom(payload);
        setQuestion(payload?.question || null);
        setAnswered(Math.min(progress.answered, progress.total));
        setTotal(progress.total);
        setCompleted(Boolean(payload?.completed));
      }
      return payload;
    } catch (requestError) {
      if (!isAbortError(requestError) && mountedRef.current) {
        setError(requestError);
        setErrorOperation('submit');
      }
      return null;
    } finally {
      submitLockRef.current = false;
      if (submitAbortRef.current === controller) submitAbortRef.current = null;
      if (mountedRef.current) setSubmitting(false);
    }
  }, [question]);

  const advance = useCallback(() => {
    if (!pendingAdvance) return;
    const progress = progressFrom(pendingAdvance);
    setQuestion(pendingAdvance.question || null);
    setAnswered(Math.min(progress.answered, progress.total));
    setTotal(progress.total);
    setCompleted(Boolean(pendingAdvance.completed));
    setVerdict(null);
    setPendingAdvance(null);
    setError(null);
    setErrorOperation(null);
  }, [pendingAdvance]);

  return {
    question,
    answered,
    total,
    completed,
    loading,
    submitting,
    error,
    errorOperation,
    verdict,
    canAdvance: Boolean(pendingAdvance),
    quotaExhausted: isQuotaError(error),
    retry: load,
    submit,
    advance,
  };
}
