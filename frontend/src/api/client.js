import { getLearnerId } from '../identity/learnerId';

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/v1').replace(/\/+$/, '');

async function request(path, { method = 'GET', body, signal } = {}) {
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
  const headers = {
    Accept: 'application/json',
    'X-Learner-Id': getLearnerId(),
  };

  if (body !== undefined && !isFormData) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`${apiBaseUrl}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
    signal,
  });

  if (response.status === 204) return null;

  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      typeof payload === 'object' && (payload?.message || payload?.error)
        ? (payload.message || payload.error)
        : `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}

/** API Gateway `/v1` client for the anonymous learner experience. */
export const apiClient = {
  initLearner: (body, options) => request('/learner/init', { method: 'POST', body, ...options }),
  getBaselineNext: (options) => request('/baseline/next', options),
  submitBaseline: (body, options) =>
    request('/baseline/submit', { method: 'POST', body, ...options }),
  getNextQuestion: (topicId, options) =>
    request(`/topic/${encodeURIComponent(topicId)}/next-question`, options),
  getHistory: (topicId, options) => request(`/topic/${encodeURIComponent(topicId)}/history`, options),
  runCheck: (body, options) => request('/run-check', { method: 'POST', body, ...options }),
  generate: (body, options) => request('/generate', { method: 'POST', body, ...options }),
  getHint: (body, options) => request('/hint', { method: 'POST', body, ...options }),
  createReflection: (body, options) =>
    request('/reflection', { method: 'POST', body, ...options }),
  getReflection: (questionId, options) => request(`/reflection/${encodeURIComponent(questionId)}`, options),
  deleteReflection: (questionId, options) =>
    request(`/reflection/${encodeURIComponent(questionId)}`, { method: 'DELETE', ...options }),
  getDemoTrace: (options) => request('/demo-trace', options),
};
