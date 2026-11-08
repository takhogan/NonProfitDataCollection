import { describe, expect, it } from 'vitest';
import { MockApiClient } from '../../api';
import { areasOfNeedCsv, toCsv } from './csv';

describe('aggregate CSV export (WEB-017)', () => {
  it('writes suppressed and no-data cells as labels, never 0', async () => {
    const api = new MockApiClient({ now: Date.parse('2026-11-07T16:00:00Z'), latencyMs: 0 });
    const data = await api.getAreasOfNeed({ level: 'sector', bucket: '24h' });
    const csv = areasOfNeedCsv(data, 'es');
    expect(csv).toContain('Datos insuficientes');
    expect(csv).toContain('Sin datos');
    const samanes = csv.split('\r\n').find((l) => l.includes('Los Samanes') && l.includes('Agua potable'))!;
    expect(samanes).not.toMatch(/,0,/);
  });

  it('quotes and neutralises formula-like values', () => {
    expect(toCsv(['a'], [['=SUM(A1)'], ['x,y']])).toBe('a\r\n\'=SUM(A1)\r\n"x,y"\r\n');
  });
});
