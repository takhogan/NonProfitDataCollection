import type { Quantity, Schedule, Weekday } from '../../api';
import { formatDate, formatNumber } from '../../locales/format';
import { translate, type Lang, LOCALES } from '../../locales/i18n';

export const WEEKDAYS: Weekday[] = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

/** Times in a schedule are Caracas wall-clock times. */
export function formatSchedule(s: Schedule, lang: Lang): string {
  const hours = `${s.start_time}–${s.end_time}`;
  if (s.kind === 'one_off') return `${formatDate(s.date, LOCALES[lang])}, ${hours}`;
  const days = WEEKDAYS.filter((d) => s.days.includes(d))
    .map((d) => translate(lang, `weekday.${d}`))
    .join(', ');
  return `${days}, ${hours}`;
}

export function formatQuantity(q: Quantity, lang: Lang): string {
  return `${formatNumber(q.value, LOCALES[lang])} ${translate(lang, `quantityUnit.${q.unit}`)}`;
}
