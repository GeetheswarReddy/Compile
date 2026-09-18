import BaselineAssessment from '../baseline/BaselineAssessment';
import PracticeScreen from '../practice/PracticeScreen';

export const TOPICS = [
  { id: 'arrays', label: 'Arrays', description: 'Work with ordered collections and scans.' },
  { id: 'strings', label: 'Strings', description: 'Build confidence with text processing.' },
  {
    id: 'hash-maps-two-pointers',
    label: 'Hash Maps / Two Pointers',
    description: 'Practice fast lookups and paired traversal.',
  },
];

export const routes = {
  home: '/',
  baseline: '/baseline',
  practice: '/practice/:topicId',
};

function normalizePath(pathname) {
  const path = pathname || '/';
  return path.length > 1 ? path.replace(/\/+$/, '') : path;
}

export function matchRoute(pathname = window.location.pathname) {
  const path = normalizePath(pathname);
  if (path === routes.baseline) return { name: 'baseline' };

  const practiceMatch = path.match(/^\/practice\/([^/]+)$/);
  if (practiceMatch && TOPICS.some((topic) => topic.id === practiceMatch[1])) {
    return { name: 'practice', topicId: practiceMatch[1] };
  }

  return { name: 'home' };
}

export function RouteView({ route }) {
  if (route.name === 'baseline') return <BaselineAssessment />;
  if (route.name === 'practice') return <PracticeScreen topicId={route.topicId} />;
  return null;
}
