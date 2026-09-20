import React, { useEffect, useMemo, useRef, useState } from 'react';
import { apiClient } from './api/client';
import { errorMessage, isAbortError } from './api/contracts';
import HintLadder from './hints/HintLadder';
import ReflectionCard from './reflection/ReflectionCard';
import PracticeHistory from './reflection/PracticeHistory';
import DemoTrace from './trace/DemoTrace';
import PracticeScreen from './practice/PracticeScreen';
import { matchRoute, RouteView, TOPICS } from './app/routes';

const DEMO_TRACE_ENABLED = import.meta.env.VITE_DEMO_TRACE === 'true';

function navigate(path) {
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function Shell({ children, onHome }) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__inner">
          <button className="app-brand" type="button" onClick={onHome} aria-label="Compile home">
            <span>Compile</span>
          </button>
          <span className="app-header__descriptor">Adaptive Python practice</span>
        </div>
      </header>
      {children}
    </div>
  );
}

function TopicSelection({ baselineCompleted }) {
  return (
    <main className="topic-selection">
      <section className="topic-hero">
        <p className="app-eyebrow">Placement preparation</p>
        <h1>Choose a topic to practice</h1>
        <p>Build interview confidence with questions matched to your current level.</p>
        <div className="baseline-callout">
          <div>
            <span className={`baseline-callout__status ${baselineCompleted ? 'is-complete' : ''}`}>
              {baselineCompleted ? 'Baseline complete' : 'Recommended first step'}
            </span>
            <h2>{baselineCompleted ? 'Your practice level is set' : 'Set your starting level'}</h2>
            <p>{baselineCompleted ? 'Your starting level now guides adaptive practice.' : 'Answer five short questions so practice starts at the right difficulty.'}</p>
          </div>
          <button className="topic-baseline-button" type="button" onClick={() => navigate('/baseline')}>
            {baselineCompleted ? 'View baseline status' : 'Take the baseline assessment'}
          </button>
        </div>
      </section>
      <section className="topic-grid" aria-label="Practice topics">
        {TOPICS.map((topic, index) => (
          <article className="topic-card" key={topic.id}>
            <span className="topic-card__number" aria-hidden="true">0{index + 1}</span>
            <div className="topic-card__content">
              <h2>{topic.label}</h2>
              <p>{topic.description}</p>
            </div>
            <button type="button" onClick={() => navigate(`/practice/${topic.id}`)}>Practice topic</button>
          </article>
        ))}
      </section>
    </main>
  );
}

function PracticeComposition({ route }) {
  const [questionId, setQuestionId] = useState('');
  const [attempted, setAttempted] = useState(false);
  return (
    <PracticeScreen
      topicId={route.topicId}
      onQuestionIdChange={setQuestionId}
      onAttemptChange={setAttempted}
      trace={DEMO_TRACE_ENABLED ? <DemoTrace key={`${questionId}-${attempted}`} enabled /> : null}
      support={(
        <div className="practice-support" aria-label="Practice support">
          <HintLadder key={`hint-${questionId}`} questionId={questionId} disabled={!questionId} />
          <details className="practice-secondary">
            <summary>Private reflection</summary>
            <div className="practice-secondary__content">
              <ReflectionCard key={`reflection-${questionId}`} questionId={questionId} disabled={!questionId || !attempted} />
            </div>
          </details>
        </div>
      )}
      history={(
        <details className="practice-secondary">
          <summary>Practice history</summary>
          <div className="practice-secondary__content">
            <PracticeHistory topicId={route.topicId} refreshKey={`${questionId}-${attempted}`} />
          </div>
        </details>
      )}
    />
  );
}

export default function App() {
  const [route, setRoute] = useState(() => matchRoute());
  const [learner, setLearner] = useState(null);
  const [initError, setInitError] = useState('');
  const [initializing, setInitializing] = useState(true);
  const [initAttempt, setInitAttempt] = useState(0);
  const initSequenceRef = useRef(0);
  const routeKey = useMemo(() => `${route.name}:${route.topicId || ''}`, [route]);

  useEffect(() => {
    const updateRoute = () => setRoute(matchRoute());
    window.addEventListener('popstate', updateRoute);
    return () => window.removeEventListener('popstate', updateRoute);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const sequence = ++initSequenceRef.current;
    setInitializing(true);
    setLearner(null);
    setInitError('');
    apiClient.initLearner({}, { signal: controller.signal }).then((payload) => {
      if (controller.signal.aborted || sequence !== initSequenceRef.current) return;
      if (!payload?.learner) throw new Error('Your progress could not be initialized. Try again.');
      setLearner(payload.learner);
      setInitError('');
      if (route.name === 'practice' && !payload.learner.baselineCompleted) navigate('/baseline');
    }).catch((error) => {
      if (!isAbortError(error) && sequence === initSequenceRef.current) {
        setInitError(errorMessage(error, 'Your progress could not be initialized. Try again.'));
      }
    }).finally(() => {
      if (!controller.signal.aborted && sequence === initSequenceRef.current) setInitializing(false);
    });
    return () => controller.abort();
  }, [initAttempt, routeKey]);

  const initialized = !initializing && !initError && Boolean(learner);

  return (
    <Shell onHome={() => navigate('/')}>
      {initError && (
        <section className="app-initialization-error" role="alert" aria-labelledby="initialization-error-title">
          <h1 id="initialization-error-title">We couldn’t load your progress.</h1>
          <p>{initError}</p>
          <button type="button" onClick={() => setInitAttempt((attempt) => attempt + 1)}>Try again</button>
        </section>
      )}
      {initializing && <p className="app-loading" role="status">Loading your progress…</p>}
      {initialized && <div key={routeKey}>
        {route.name === 'home' ? <TopicSelection baselineCompleted={Boolean(learner.baselineCompleted)} /> : null}
        {route.name === 'baseline' ? <RouteView route={route} /> : null}
        {route.name === 'practice' && learner.baselineCompleted ? <PracticeComposition route={route} /> : null}
      </div>}
    </Shell>
  );
}
