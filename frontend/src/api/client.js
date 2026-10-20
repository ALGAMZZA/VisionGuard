import axios from 'axios';

const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_BASE_URL || '/api',
  timeout: 60000,
});

export function getApiErrorMessage(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (error?.code === 'ECONNABORTED') return '요청 시간이 초과되었습니다.';
  const messages = {
    400: '입력 정보를 확인해 주세요.',
    404: '요청한 이벤트 또는 처리된 스트림이 없습니다.',
    409: '프레임 순서 또는 스트림 정보가 충돌합니다. 새 영상에는 새 streamId를 사용해 주세요.',
    413: '이미지 또는 요청 크기가 너무 큽니다.',
    502: 'AI 분석에 실패했습니다.',
  };
  if (!error?.response) return '서버에 연결할 수 없습니다.';
  return messages[error.response.status] || '서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.';
}

export default apiClient;
