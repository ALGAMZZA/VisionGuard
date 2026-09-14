import ExcelJS from 'exceljs';
import { getRiskEvents } from '../api/visionGuardApi';
import { collectRiskEvents, createRiskEventsWorkbook } from './exportRiskEvents';
import { getDateRange } from './riskEvent';

jest.mock('../api/visionGuardApi', () => ({ getRiskEvents: jest.fn() }));
beforeEach(() => jest.clearAllMocks());

test('collects every filtered page and deduplicates events shifted by new arrivals', async () => {
  getRiskEvents.mockResolvedValueOnce({ content: [{ id: 3 }, { id: 2 }], totalPages: 2 });
  getRiskEvents.mockResolvedValueOnce({ content: [{ id: 2 }, { id: 1 }], totalPages: 2 });
  const signal = new AbortController().signal;
  expect(await collectRiskEvents({ date: '2026-09-13', cameraId: 'camera-1' }, { signal })).toEqual([{ id: 3 }, { id: 2 }, { id: 1 }]);
  expect(getRiskEvents).toHaveBeenLastCalledWith({ cameraId: 'camera-1', ...getDateRange('2026-09-13'), page: 1, size: 100 }, { signal });
});

test('does not silently export partial results on a failed page', async () => {
  getRiskEvents.mockResolvedValueOnce({ content: [{ id: 3 }], totalPages: 2 });
  getRiskEvents.mockRejectedValueOnce(new Error('network failure'));
  await expect(collectRiskEvents({})).rejects.toThrow('network failure');
});

test('xlsx round trip preserves dates, links, missing values, numeric zero and literal text', async () => {
  const workbook = await createRiskEventsWorkbook([{
    id: 7, capturedAt: '2026-09-13T01:23:45Z', cameraId: '=1+1', level: 'DANGER',
    status: 'CLOSED', personTrackId: null, frameCount: 0,
  }], 'https://visionguard.example');
  const saved = new ExcelJS.Workbook();
  await saved.xlsx.load(await workbook.xlsx.writeBuffer());
  const sheet = saved.getWorksheet('위험 이력');
  expect(sheet.rowCount).toBe(2);
  expect(sheet.getCell('B2').value.toISOString()).toBe('2026-09-13T01:23:45.000Z');
  expect(sheet.getCell('D2').value).toBe('=1+1');
  expect(sheet.getCell('D2').type).toBe(ExcelJS.ValueType.String);
  expect(sheet.getCell('F2').value).toBe('위험');
  expect(sheet.getCell('G2').value).toBe('미제공');
  expect(sheet.getCell('H2').value).toBe('종료');
  expect(sheet.getCell('I2').value).toContain('서버 영상 미저장');
  expect(sheet.getCell('J2').value.hyperlink).toBe('https://visionguard.example/alerts?eventId=7');
  expect(sheet.getCell('N2').value).toBeNull();
  expect(sheet.getCell('R2').value).toBe(0);
  expect(sheet.views[0].ySplit).toBe(1);
  expect(sheet.autoFilter).toBe('A1:S1');
});
