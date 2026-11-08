import { describe, expect, it } from 'vitest';
import { assumeCountryCode, classify, cleanNumber, splitPasted, summarize } from './phone';

describe('cleanNumber', () => {
  it('strips spaces, dashes, parentheses and keeps one leading +', () => {
    expect(cleanNumber('+1 (305) 555-0142')).toBe('+13055550142');
    expect(cleanNumber(' 305.555.0142 ')).toBe('3055550142');
  });
});

describe('classify', () => {
  it('accepts a valid E.164 number', () => {
    expect(classify('+58 412 555 0142').status).toBe('valid');
    expect(classify('+58 412 555 0142').normalized).toBe('+584125550142');
  });
  it('flags a number without a country code (no guessing)', () => {
    const p = classify('305 555 0142');
    expect(p.status).toBe('missing_country_code');
    expect(p.normalized).toBe('3055550142');
  });
  it('rejects a too-short number that already has a country code', () => {
    expect(classify('+12').status).toBe('invalid');
  });
  it('treats empty / non-numeric input as invalid', () => {
    expect(classify('   ').status).toBe('invalid');
    expect(classify('nope').status).toBe('invalid');
  });
});

describe('splitPasted', () => {
  it('splits on commas, spaces, semicolons and newlines', () => {
    expect(splitPasted('+13055550142, +13055550143\n+13055550144;+13055550145')).toEqual([
      '+13055550142', '+13055550143', '+13055550144', '+13055550145',
    ]);
  });
});

describe('summarize', () => {
  it('counts valid, missing-code, and removes duplicates', () => {
    const s = summarize(['+13055550142', '+1 305 555 0142', '305 555 9999', 'nope', '+13055550143']);
    expect(s.valid.map((v) => v.normalized)).toEqual(['+13055550142', '+13055550143']);
    expect(s.duplicatesRemoved).toBe(1);
    expect(s.needsCountryCode).toHaveLength(1);
    expect(s.invalid).toHaveLength(1);
  });
});

describe('assumeCountryCode', () => {
  it('prepends a code only to numbers missing one', () => {
    const classified = ['305 555 0142', '+13055550143'].map(classify);
    const fixed = assumeCountryCode(classified, '+1');
    expect(fixed[0]?.status).toBe('valid');
    expect(fixed[0]?.normalized).toBe('+13055550142');
    expect(fixed[1]?.normalized).toBe('+13055550143'); // untouched
  });
});
