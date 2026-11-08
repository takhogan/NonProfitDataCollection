import { describe, expect, it } from 'vitest';
import { formatDateTime, formatRelative } from './format';
import { translate } from './i18n';
import { es } from './es';
import { en } from './en';

describe('Caracas time (NFR-02, WEB-003)', () => {
  it('shows UTC instants in America/Caracas (UTC-4)', () => {
    const s = formatDateTime('2026-11-07T14:05:00Z', 'en-US');
    expect(s).toMatch(/10:05/);
    expect(s).toMatch(/AM/);
  });

  it('marks approximate times with "aprox."', () => {
    expect(formatDateTime('2026-11-07T14:05:00Z', 'es-VE', { approximate: true })).toMatch(/^aprox\. /);
  });

  it('formats relative age', () => {
    const now = Date.parse('2026-11-07T16:00:00Z');
    expect(formatRelative('2026-11-07T13:00:00Z', 'es-VE', now)).toMatch(/3 h/);
  });
});

describe('i18n', () => {
  it('defaults to Spanish copy with plurals', () => {
    expect(translate('es', 'unit.needs', { count: 1 })).toBe('necesidad activa');
    expect(translate('es', 'unit.needs', { count: 4 })).toBe('necesidades activas');
    expect(translate('en', 'unit.needs', { count: 1 })).toBe('active need');
  });

  it('English defines every Spanish key', () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(es).sort());
  });
});
