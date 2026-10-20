import { useEffect, useState } from 'react';
import { getRiskEvents } from '../api/visionGuardApi';
import { getApiErrorMessage } from '../api/client';

export default function useRecentEvents(cameraId) {
  const [state, setState] = useState({ events: [], loading: true, error: '' });
  useEffect(() => {
    if (!cameraId) {
      setState({ events: [], loading: false, error: '' });
      return undefined;
    }
    const controller = new AbortController();
    let timer;
    setState({ events: [], loading: true, error: '' });
    async function poll() {
      try {
        const result = await getRiskEvents({ cameraId, size: 4 }, { signal: controller.signal });
        if (!controller.signal.aborted) setState({ events: result.content, loading: false, error: '' });
      } catch (error) {
        if (!controller.signal.aborted) setState({ events: [], loading: false, error: getApiErrorMessage(error) });
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 5000);
      }
    }
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [cameraId]);
  return state;
}
