/**
 * WEB-017 (partial): client-side CSV of the current view. Rows come from API
 * responses that are already suppressed (DOM-044), and suppressed / no-data
 * cells are written as labels, never as 0. The server export (API-060, with
 * XLSX and audit) replaces this once it exists.
 */
import type { Activity, AreasOfNeedResponse, CoverageResponse, IndicatorCell } from '../../api';
import { translate, type Lang } from '../../locales/i18n';

type Cell = string | number | null;

export function toCsv(header: string[], rows: Cell[][]): string {
  const esc = (v: Cell) => {
    if (v === null) return '';
    const s = String(v);
    // Neutralise spreadsheet formula injection as well as quoting.
    const safe = /^[=+\-@\t\r]/.test(s) ? `'${s}` : s;
    return /[",\n;]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
  };
  return [header, ...rows].map((r) => r.map(esc).join(',')).join('\r\n') + '\r\n';
}

function countOrLabel(cell: IndicatorCell, v: number | null, lang: Lang): Cell {
  if (cell.coverage_label === 'none') return translate(lang, 'honest.noData');
  if (cell.suppressed) return translate(lang, 'honest.insufficient');
  return v;
}

function cellColumns(cell: IndicatorCell, lang: Lang): Cell[] {
  return [
    cell.area.name,
    cell.area.parent_name,
    cell.category ? translate(lang, `category.${cell.category}`) : null,
    translate(lang, `bucket.${cell.bucket}`),
    countOrLabel(cell, cell.active_needs, lang),
    countOrLabel(cell, cell.distinct_reporters, lang),
    countOrLabel(cell, cell.people_affected_known, lang),
    countOrLabel(cell, cell.people_affected_unknown_count, lang),
    countOrLabel(cell, cell.urgency_mix?.urgent ?? null, lang),
    cell.freshness,
    translate(lang, `coverageLabel.${cell.coverage_label}`),
    translate(lang, `confidence.${cell.confidence.level}`),
    cell.confidence.reasons.map((r) => translate(lang, `confidenceReason.${r}`)).join('; '),
    cell.method_version,
    cell.input_watermark,
  ];
}

function cellHeader(lang: Lang): string[] {
  return [
    'csv.area',
    'csv.parish',
    'csv.category',
    'csv.bucket',
    'csv.activeNeeds',
    'csv.reporters',
    'csv.peopleKnown',
    'csv.peopleUnknownCount',
    'csv.urgent',
    'csv.freshnessUtc',
    'csv.coverageLabel',
    'csv.confidence',
    'csv.confidenceReasons',
    'csv.methodVersion',
    'csv.inputWatermarkUtc',
  ].map((k) => translate(lang, k as Parameters<typeof translate>[1]));
}

export function areasOfNeedCsv(data: AreasOfNeedResponse, lang: Lang): string {
  const rows = [
    ...data.items.map((r) => [r.rank, ...cellColumns(r.cell, lang)]),
    ...data.unranked.map((c) => [null, ...cellColumns(c, lang)]),
  ];
  return toCsv([translate(lang, 'csv.rank'), ...cellHeader(lang)], rows);
}

export function coverageCsv(data: CoverageResponse, lang: Lang): string {
  const rows = data.items.map((c) => [
    translate(lang, `coverage.status.${c.status}`),
    c.high_need ? translate(lang, 'common.yes') : translate(lang, 'common.no'),
    c.activities.map((a) => a.provider_organization.name).join('; '),
    ...cellColumns(c.need, lang),
  ]);
  return toCsv(
    [translate(lang, 'csv.coverageStatus'), translate(lang, 'csv.highNeed'), translate(lang, 'csv.providers'), ...cellHeader(lang)],
    rows,
  );
}

export function activitiesCsv(items: Activity[], lang: Lang): string {
  const rows = items.map((a) => [
    a.provider_organization.name,
    translate(lang, `activityType.${a.type}`),
    translate(lang, `category.${a.category}`),
    a.areas.map((x) => x.name).join('; '),
    translate(lang, `activityStatus.${a.status}`),
    a.capacity ? `${a.capacity.value} ${translate(lang, `quantityUnit.${a.capacity.unit}`)}` : null,
    a.public_location?.name ?? null,
    a.last_confirmed_at,
  ]);
  return toCsv(
    ['csv.provider', 'csv.type', 'csv.category', 'csv.areas', 'csv.status', 'csv.capacity', 'csv.publicLocation', 'csv.lastConfirmedUtc'].map(
      (k) => translate(lang, k as Parameters<typeof translate>[1]),
    ),
    rows,
  );
}
