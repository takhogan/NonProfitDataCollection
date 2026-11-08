/**
 * Phone-number normalization for the campaign contacts step.
 *
 * We normalize to E.164 (a leading `+` and up to 15 digits). We deliberately do
 * NOT guess a country code: a number without a leading `+` is flagged as
 * "missing country code" so the user fixes it (or applies "+1 to all"), rather
 * than silently assuming a country and dialing the wrong person.
 */

export type PhoneStatus = 'valid' | 'missing_country_code' | 'invalid';

export interface ParsedNumber {
  raw: string;          // what the user entered
  normalized: string;   // E.164 if valid, else best-effort cleaned form
  status: PhoneStatus;
}

export interface ParseSummary {
  valid: ParsedNumber[];          // unique, E.164
  needsCountryCode: ParsedNumber[];
  invalid: ParsedNumber[];
  duplicatesRemoved: number;
}

const MAX_E164_DIGITS = 15;
const MIN_DIGITS = 8; // shortest plausible national+country number for our use

/** Strip spaces, dashes, parentheses, dots. Keep a single leading +. */
export function cleanNumber(raw: string): string {
  const trimmed = raw.trim();
  const hasPlus = trimmed.startsWith('+');
  const digits = trimmed.replace(/[^\d]/g, '');
  return (hasPlus ? '+' : '') + digits;
}

export function classify(raw: string): ParsedNumber {
  const cleaned = cleanNumber(raw);
  const digits = cleaned.replace(/\D/g, '');
  if (digits.length === 0) {
    return { raw, normalized: cleaned, status: 'invalid' };
  }
  if (!cleaned.startsWith('+')) {
    // Has digits but no country code — fixable, don't guess.
    return { raw, normalized: digits, status: 'missing_country_code' };
  }
  if (digits.length < MIN_DIGITS || digits.length > MAX_E164_DIGITS) {
    return { raw, normalized: cleaned, status: 'invalid' };
  }
  return { raw, normalized: '+' + digits, status: 'valid' };
}

/** Split a pasted blob on commas, semicolons, whitespace, or newlines. */
export function splitPasted(text: string): string[] {
  return text
    .split(/[\s,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Apply a default country calling code (e.g. "1") to every number that is
 * missing one. Numbers that are already valid or truly invalid are untouched. */
export function assumeCountryCode(items: ParsedNumber[], code: string): ParsedNumber[] {
  const cc = code.replace(/\D/g, '');
  return items.map((it) => {
    if (it.status !== 'missing_country_code') return it;
    return classify('+' + cc + it.normalized);
  });
}

/** Classify a list, dedupe valid E.164 numbers, and summarize. */
export function summarize(rawNumbers: string[]): ParseSummary {
  const parsed = rawNumbers.map(classify);
  const seen = new Set<string>();
  const valid: ParsedNumber[] = [];
  let duplicatesRemoved = 0;
  const needsCountryCode: ParsedNumber[] = [];
  const invalid: ParsedNumber[] = [];

  for (const p of parsed) {
    if (p.status === 'valid') {
      if (seen.has(p.normalized)) {
        duplicatesRemoved += 1;
        continue;
      }
      seen.add(p.normalized);
      valid.push(p);
    } else if (p.status === 'missing_country_code') {
      needsCountryCode.push(p);
    } else {
      invalid.push(p);
    }
  }
  return { valid, needsCountryCode, invalid, duplicatesRemoved };
}
