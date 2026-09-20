import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiClient } from '../api/client';

import {
  unwrapQuestion, readOnlyFrom, boundedFailures, normalizeVerdict,
  errorMessage, isAbortError, isQuotaError,
} from '../api/contracts';

function waitFor(delay, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('The request was cancelled.', 'AbortError'));
      return;
    }
    const timeout = setTimeout(resolve, delay);
    signal?.addEventListener('abort', () => {
      clearTimeout(timeout);
      reject(new DOMException('The request was cancelled.', 'AbortError'));
    }, { once: true });
  });
}

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
  const loadSequenceRef = useRef(0);
  const loadControllerRef = useRef(null);
  const submitLockRef = useRef(false);
  const generateLockRef = useRef(false);
  const operationControllersRef = useRef(new Set());
  const mountedRef = useRef(true);

  const loadQuestion = useCallback(async () => {
    if (!topicId) return null;
    loadControllerRef.current?.abort();
    const controller = new AbortController();
    loadControllerRef.current = controller;
    const { signal } = controller;
    const sequence = ++loadSequenceRef.current;
    setLoading(true);
    setError('');
    setVerdict(null);
    setTagRevealed(false);
    try {
      const payload = await apiClient.getNextQuestion(topicId, { signal });
      if (signal?.aborted || sequence !== loadSequenceRef.current || !mountedRef.current) return null;
      const nextQuestion = unwrapQuestion(payload);
      setQuestion(nextQuestion);
      setCode(nextQuestion?.starterCode || '');
      setReadOnly(readOnlyFrom(payload, nextQuestion));
      return nextQuestion;
    } catch (requestError) {
      if (!isAbortError(requestError) && sequence === loadSequenceRef.current && mountedRef.current) {
        setError(errorMessage(requestError, 'Unable to load a question.'));
      }
      return null;
    } finally {
      if (!signal?.aborted && sequence === loadSequenceRef.current && mountedRef.current) setLoading(false);
    }
  }, [topicId]);

  useEffect(() => {
    mountedRef.current = true;
    loadQuestion();
    return () => {
      mountedRef.current = false;
      loadControllerRef.current?.abort();
      for (const operationController of operationControllersRef.current) operationController.abort();
      operationControllersRef.current.clear();
    };
  }, [loadQuestion]);

  const runCheck = useCallback(async () => {
    if (readOnly || !question?.questionId || submitLockRef.current) return null;
    submitLockRef.current = true;
    const controller = new AbortController();
    operationControllersRef.current.add(controller);
    setSubmitting(true);
    setError('');
    try {
      const payload = await apiClient.runCheck(
        { questionId: question.questionId, code },
        { signal: controller.signal },
      );
      if (controller.signal.aborted || !mountedRef.current) return null;
      const nextVerdict = normalizeVerdict(payload);
      setVerdict(nextVerdict);
      if (readOnlyFrom(payload, question)) setReadOnly(true);
      return nextVerdict;
    } catch (requestError) {
      if (!isAbortError(requestError) && mountedRef.current) {
        if (isQuotaError(requestError)) setReadOnly(true);
        setError(errorMessage(requestError, 'Run & Check could not be completed.'));
      }
      return null;
    } finally {
      submitLockRef.current = false;
      operationControllersRef.current.delete(controller);
      if (mountedRef.current) setSubmitting(false);
    }
  }, [code, question, readOnly]);

  const generate = useCallback(async () => {
    if (readOnly || generateLockRef.current || !topicId) return null;
    generateLockRef.current = true;
    const controller = new AbortController();
    operationControllersRef.current.add(controller);
    setGenerating(true);
    setError('');
    setVerdict(null);
    try {
      await apiClient.generate({ topicId }, { signal: controller.signal });
      // The worker continues after this bounded browser wait. Late results are
      // offered on the next question request if still near current mastery.
      await waitFor(8000, controller.signal);
      const payload = await apiClient.getNextQuestion(topicId, { signal: controller.signal });
      if (controller.signal.aborted || !mountedRef.current) return null;
      const nextQuestion = unwrapQuestion(payload);
      if (nextQuestion) {
        setQuestion(nextQuestion);
        setCode(nextQuestion.starterCode || '');
        setTagRevealed(false);
      }
      setReadOnly(readOnlyFrom(payload, nextQuestion) || readOnly);
      return nextQuestion;
    } catch (requestError) {
      if (!isAbortError(requestError) && mountedRef.current) {
        if (isQuotaError(requestError)) setReadOnly(true);
        setError(errorMessage(requestError, 'Question generation could not be completed.'));
      }
      return null;
    } finally {
      generateLockRef.current = false;
      operationControllersRef.current.delete(controller);
      if (mountedRef.current) setGenerating(false);
    }
  }, [readOnly, topicId]);

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
    loadQuestion,
  }), [code, error, generate, generating, loadQuestion, loading, question, readOnly, runCheck, submitting, tagRevealed, verdict]);
}

export { boundedFailures, normalizeVerdict, unwrapQuestion };
