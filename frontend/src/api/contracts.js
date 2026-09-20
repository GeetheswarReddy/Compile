function unwrapQuestion(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const candidate = 'question' in payload ? payload.question : payload;
  return candidate && typeof candidate.questionId === 'string' ? candidate : null;
}

function readOnlyFrom(payload, question) {
  const learner = payload?.learner || payload?.learnerState || payload?.state || {};
  const quota = payload?.quota || {};
  const executionCount = learner.runCheckActions ?? quota.runCheckActions;
  const generationCount = learner.generationRequests ?? quota.generationRequests;
  return Boolean(
    payload?.readOnly ||
      payload?.isReadOnly ||
      quota.readOnly ||
      learner.readOnly ||
      executionCount >= 5 ||
      generationCount >= 2 ||
      question?.readOnly,
  );
}

function boundedFailures(verdict) {
  const failures = Array.isArray(verdict?.failedCases)
    ? verdict.failedCases
    : Array.isArray(verdict?.failures)
      ? verdict.failures
      : [];
  return failures.slice(0, 2);
}

function normalizeVerdict(payload) {
  if (!payload || typeof payload !== 'object') return null;
  return {
    ...payload,
    passed: Boolean(payload.passed ?? payload.correct),
    failedCases: boundedFailures(payload),
  };
}

function isAbortError(error) {
  return error?.name === 'AbortError';
}

function isQuotaError(error) {
  return error?.kind === 'quota' || error?.status === 429;
}

function errorMessage(error, fallback) {
  return typeof error?.message === 'string' && error.message.trim() ? error.message : fallback;
}

export { unwrapQuestion, readOnlyFrom, boundedFailures, normalizeVerdict, isAbortError, isQuotaError, errorMessage };
