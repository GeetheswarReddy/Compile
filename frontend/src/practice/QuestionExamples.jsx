import React from 'react';

export default function QuestionExamples({ examples = [] }) {
  if (!examples.length) return null;
  return <div className="question-examples"><h3>Examples</h3>{examples.map((example, index) =>
    <pre key={index}><code>{`Input: ${JSON.stringify(example.input)}\nOutput: ${JSON.stringify(example.expected)}`}</code></pre>
  )}</div>;
}
