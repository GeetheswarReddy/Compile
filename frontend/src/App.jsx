import React, { useEffect, useMemo, useState } from 'react';
import HintLadder from './hints/HintLadder';
import ReflectionCard from './reflection/ReflectionCard';
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
        <button className="app-brand" type="button" onClick={onHome}>Compile</button>
        <span>Adaptive Python practice</span>
      </header>
      {children}
    </div>
  );
}

function TopicSelection() {
  return (
    <main className="topic-selection">
      <section className="topic-hero">
        <p className="app-eyebrow">Placement preparation</p>
        <h1>Choose a topic to practice.</h1>
        <p>Start with a short baseline assessment, then work through questions matched to your current level.</p>
        <button className="topic-baseline-button" type="button" onClick={() => navigate('/baseline')}>
          Take the baseline assessment
        </button>
      </section>
      <section className="topic-grid" aria-label="Practice topics">
        {TOPICS.map((topic) => (
          <article className="topic-card" key={topic.id}>
            <h2>{topic.label}</h2>
            <p>{topic.description}</p>
            <button type="button" onClick={() => navigate(`/practice/${topic.id}`)}>Practice topic</button>
          </article>
        ))}
      </section>
    </main>
  );
}

function PracticeComposition({ route }) {
  const [questionId, setQuestionId] = useState('');
  return (
    <>
      <PracticeScreen topicId={route.topicId} onQuestionIdChange={setQuestionId} />
      <div className="practice-support" aria-label="Practice support">
        <HintLadder questionId={questionId} disabled={!questionId} />
        <ReflectionCard questionId={questionId} disabled={!questionId} />
      </div>
      <DemoTrace enabled={DEMO_TRACE_ENABLED} />
    </>
  );
}

export default function App() {
  const [route, setRoute] = useState(() => matchRoute());
  const routeKey = useMemo(() => `${route.name}:${route.topicId || ''}`, [route]);

  useEffect(() => {
    const updateRoute = () => setRoute(matchRoute());
    window.addEventListener('popstate', updateRoute);
    return () => window.removeEventListener('popstate', updateRoute);
  }, []);

  return (
    <Shell onHome={() => navigate('/')}>
      <div key={routeKey}>
        {route.name === 'home' ? <TopicSelection /> : null}
        {route.name === 'baseline' ? <RouteView route={route} /> : null}
        {route.name === 'practice' ? <PracticeComposition route={route} /> : null}
      </div>
    </Shell>
  );
}
