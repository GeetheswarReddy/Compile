const LEARNER_ID_STORAGE_KEY = 'compile.learner-id';

function createLearnerId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16);
    const value = character === 'x' ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });
}

/**
 * Returns the anonymous learner identifier for this browser.
 * It is created once and retained in localStorage between visits.
 *
 * @returns {string}
 */
export function getLearnerId() {
  const storedId = window.localStorage.getItem(LEARNER_ID_STORAGE_KEY);

  if (storedId) {
    return storedId;
  }

  const learnerId = createLearnerId();
  window.localStorage.setItem(LEARNER_ID_STORAGE_KEY, learnerId);
  return learnerId;
}
