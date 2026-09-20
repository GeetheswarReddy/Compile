import { getLearnerId } from '../identity/learnerId';

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/v1').replace(/\/+$/, '');
const DEFAULT_REQUEST_TIMEOUT_MS = 15000;

function cleanText(value, fallback = '') {
  if (typeof value !== 'string') return fallback;
  const cleaned = value.replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/\s+/g, ' ').trim();
  return cleaned.slice(0, 300) || fallback;
}

function diagnosticPayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return undefined;
  const allowed = ['error', 'message', 'code', 'requestId', 'readOnly', 'baselineRequired'];
  const diagnostics = {};
  for (const key of allowed) {
    const value = payload[key];
    if (typeof value === 'boolean' || typeof value === 'number') diagnostics[key] = value;
    if (typeof value === 'string') diagnostics[key] = cleanText(value);
  }
  return Object.keys(diagnostics).length ? diagnostics : undefined;
}

function kindForStatus(status) {
  if (status === 429) return 'quota';
  if (status === 408 || status === 504) return 'timeout';
  if (status >= 500) return 'server';
  return 'request';
}

export class ApiError extends Error {
  constructor(message, { kind, status, payload, requestId } = {}) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind || 'request';
    if (status !== undefined) this.status = status;
    this.payload = diagnosticPayload(payload);
    this.diagnostics = {
      ...(requestId ? { requestId: cleanText(requestId) } : {}),
      ...(this.payload?.code ? { code: this.payload.code } : {}),
    };
  }
}

function abortError() {
  return new DOMException('The request was cancelled.', 'AbortError');
}

async function request(path, { method = 'GET', body, signal, timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS } = {}) {
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
  const headers = {
    Accept: 'application/json',
    'X-Learner-Id': getLearnerId(),
  };

  if (body !== undefined && !isFormData) {
    headers['Content-Type'] = 'application/json';
  }

  const controller = new AbortController();
  let timedOut = false;
  const onAbort = () => controller.abort();
  if (signal?.aborted) throw abortError();
  signal?.addEventListener('abort', onAbort, { once: true });
  const timeout = Number.isFinite(timeoutMs) && timeoutMs > 0
    ? setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs)
    : null;
  const cleanup = () => {
    if (timeout !== null) clearTimeout(timeout);
    signal?.removeEventListener('abort', onAbort);
  };

  let response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    cleanup();
    if (signal?.aborted) throw abortError();
    if (timedOut) {
      throw new ApiError('The service took too long to respond. Try again.', { kind: 'timeout' });
    }
    if (error instanceof ApiError) throw error;
    throw new ApiError('We couldn’t reach the service. Check your connection and try again.', {
      kind: 'connectivity',
    });
  }

  if (response.status === 204) {
    cleanup();
    return null;
  }

  const contentType = response.headers.get('content-type') || '';
  let payload;
  try {
    payload = contentType.includes('application/json')
      ? await response.json()
      : await response.text();
  } catch {
    cleanup();
    if (signal?.aborted) throw abortError();
    if (timedOut) {
      throw new ApiError('The service took too long to respond. Try again.', { kind: 'timeout' });
    }
    throw new ApiError('The service returned an unreadable response. Try again.', {
      kind: 'server',
      status: response.status,
      requestId: response.headers.get('x-request-id') || response.headers.get('x-amzn-requestid'),
    });
  }
  cleanup();

  if (!response.ok) {
    const serverMessage =
      typeof payload === 'object' && (payload?.message || payload?.error)
        ? (payload.message || payload.error)
        : '';
    const kind = kindForStatus(response.status);
    const fallback = kind === 'quota'
      ? 'The execution quota is exhausted. Learning material remains available.'
      : kind === 'server'
        ? 'The service could not complete this request. Try again.'
        : `The request could not be completed (${response.status}).`;
    throw new ApiError(cleanText(serverMessage, fallback), {
      kind,
      status: response.status,
      payload,
      requestId: response.headers.get('x-request-id') || response.headers.get('x-amzn-requestid'),
    });
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

export { DEFAULT_REQUEST_TIMEOUT_MS };
