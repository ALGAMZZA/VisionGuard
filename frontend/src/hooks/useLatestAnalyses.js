import { useEffect, useState } from 'react';
import { CAMERA_IDS, getLatestAnalysis } from '../api/visionGuardApi';
import { getApiErrorMessage } from '../api/client';

// Wait for each round to finish so slow inference never causes overlapping polls.
export default function useLatestAnalyses() {
  const [cameras, setCameras] = useState(() => CAMERA_IDS.map((id) => ({ id, loading: true })));
  useEffect(() => {
    const controller = new AbortController();
    let timer;
    async function poll() {
      const next = await Promise.all(CAMERA_IDS.map(async (id) => {
        try {
          const analysis = await getLatestAnalysis(id, { signal: controller.signal });
          return { id, analysis, loading: false, stale: Date.now() - Date.parse(analysis.capturedAt) > 15000 };
        } catch (error) {
          return { id, loading: false, error: error?.response?.status === 404 ? '분석 데이터 대기 중' : getApiErrorMessage(error) };
        }
      }));
      if (controller.signal.aborted) return;
      setCameras(next);
      timer = setTimeout(poll, 3000);
    }
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, []);
  return cameras;
}
