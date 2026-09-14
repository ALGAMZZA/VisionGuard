import apiClient from './client';

export const DEFAULT_CAMERA_ID = process.env.REACT_APP_CAMERA_ID || 'camera-1';
export const CAMERA_IDS = [...new Set((process.env.REACT_APP_CAMERA_IDS || `${DEFAULT_CAMERA_ID},camera-2`).split(',').map((id) => id.trim()).filter(Boolean))];

export async function getLatestAnalysis(cameraId, { signal } = {}) {
  const { data } = await apiClient.get('/analyses/latest', { params: { cameraId }, signal });
  return data;
}

/** 이미지 한 장을 분석합니다. 같은 스트림은 이전 요청을 await한 뒤 호출하세요.
 * 재시도 시 file과 모든 메타데이터를 그대로 재사용해야 합니다.
 * @param {{file: File|Blob, cameraId: string, frameId: string, capturedAt: string, streamId?: string, fps?: number}} frame
 * @returns {Promise<{eventId: number|null, eventIds: number[], cameraId: string, streamId: string, capturedAt: string, aiMode: string, prediction: object}>}
 */
export async function analyzeFrame({ file, cameraId, frameId, capturedAt, streamId, fps }, { signal } = {}) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('cameraId', cameraId);
  formData.append('frameId', frameId);
  formData.append('capturedAt', capturedAt);
  if (streamId !== undefined) formData.append('streamId', streamId);
  if (fps !== undefined) formData.append('fps', String(fps));
  // Content-Type boundary는 브라우저가 설정합니다.
  const { data } = await apiClient.post('/analyses', formData, { signal });
  return data;
}

/** from/to: UTC 오프셋을 포함한 ISO 8601. page는 0부터 시작합니다.
 * level/status/streamId 필터는 서버가 지원하지 않습니다.
 * @returns {Promise<{content: object[], page: number, size: number, totalElements: number, totalPages: number}>}
 */
export async function getRiskEvents({ cameraId, from, to, page = 0, size = 20 } = {}, { signal } = {}) {
  const { data } = await apiClient.get('/risk-events', {
    params: { cameraId, from, to, page, size }, signal,
  });
  return data;
}

/** 응답은 { event, prediction }. prediction 내부 snake_case를 유지합니다. */
export async function getRiskEvent(id, { signal } = {}) {
  const { data } = await apiClient.get(`/risk-events/${encodeURIComponent(id)}`, { signal });
  return data;
}

/** 마지막 분석 요청 완료 후 호출. endedAt은 마지막 capturedAt 이상이어야 합니다.
 * 재시도에는 동일한 cameraId/streamId/endedAt을 사용하세요.
 */
export async function endStream({ cameraId, streamId, endedAt }, { signal } = {}) {
  const { data } = await apiClient.post('/streams/end', { cameraId, streamId, endedAt }, { signal });
  return data;
}
