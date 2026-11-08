/** NFR-02 / WEB-003: everything is shown in Caracas time. */
export const TIME_ZONE = 'America/Caracas';

export function formatDateTime(iso: string, locale: string, opts: { approximate?: boolean } = {}): string {
  const s = new Intl.DateTimeFormat(locale, {
    timeZone: TIME_ZONE,
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(iso));
  return opts.approximate ? `${locale.startsWith('es') ? 'aprox.' : 'approx.'} ${s}` : s;
}

export function formatDate(isoOrYmd: string, locale: string): string {
  // Plain YYYY-MM-DD dates are already Caracas-local calendar dates.
  const d = /^\d{4}-\d{2}-\d{2}$/.test(isoOrYmd) ? new Date(`${isoOrYmd}T12:00:00-04:00`) : new Date(isoOrYmd);
  return new Intl.DateTimeFormat(locale, { timeZone: TIME_ZONE, weekday: 'short', day: 'numeric', month: 'short' }).format(d);
}

export function formatRelative(iso: string, locale: string, now: number = Date.now()): string {
  const diffSec = Math.round((Date.parse(iso) - now) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto', style: 'short' });
  const abs = Math.abs(diffSec);
  if (abs < 60) return rtf.format(Math.round(diffSec), 'second');
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), 'hour');
  return rtf.format(Math.round(diffSec / 86400), 'day');
}

export function formatNumber(n: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(n);
}

export function formatPercent(share: number, locale: string): string {
  return new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 0 }).format(share);
}
