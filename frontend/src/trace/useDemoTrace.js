import { useEffect, useState } from 'react';
import { apiClient } from '../api/client';

/** Load demo-only provenance, retry, and mastery records. */
export function useDemoTrace(enabled) {
  const [state, setState] = useState({ entries: [], loading: false, error: null });

  useEffect(() => {
    if (!enabled) {
      setState({ entries: [], loading: false, error: null });
      return undefined;
    }

    const controller = new AbortController();
    setState({ entries: [], loading: true, error: null });

    apiClient
      .getDemoTrace({ signal: controller.signal })
      .then((payload) => {
        if (!controller.signal.aborted) {
          setState({
            entries: Array.isArray(payload?.entries) ? payload.entries : [],
            loading: false,
            error: null,
          });
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setState({ entries: [], loading: false, error });
        }
      });

    return () => controller.abort();
  }, [enabled]);

  return state;
}
