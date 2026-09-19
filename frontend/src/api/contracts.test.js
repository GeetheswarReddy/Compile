import test from 'node:test';
import assert from 'node:assert/strict';
import { unwrapQuestion, normalizeVerdict, readOnlyFrom } from './contracts.js';

test('completion and async generation responses never become editor questions', () => {
  assert.equal(unwrapQuestion({ question: null, completed: true }), null);
  assert.equal(unwrapQuestion({ executionArn: 'pending', topic: 'Arrays' }), null);
  const question = { questionId: 'q1', starterCode: 'def solve(): pass' };
  assert.equal(unwrapQuestion({ question }), question);
});

test('deployed verdict preserves false and bounds failed-case disclosure', () => {
  const verdict = normalizeVerdict({ passed: false, failedCases: [1, 2, 3], scored: false });
  assert.equal(verdict.passed, false);
  assert.equal(verdict.scored, false);
  assert.deepEqual(verdict.failedCases, [1, 2]);
});

test('server quota and persisted learner counts disable execution controls', () => {
  assert.equal(readOnlyFrom({ learner: {runCheckActions: 4, generationRequests: 1} }), false);
  assert.equal(readOnlyFrom({ learner: {runCheckActions: 5} }), true);
  assert.equal(readOnlyFrom({ learner: {generationRequests: 2} }), true);
  assert.equal(readOnlyFrom({ readOnly: true }), true);
});
