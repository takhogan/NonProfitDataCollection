/**
 * Mock-side approximations of the domain rules (DOM-040–044, DOM-052) so the
 * UI can be exercised. The real rules live in the backend; this file is not a
 * specification.
 */
import type {
  Activity,
  AreaOfNeed,
  AreaRef,
  Bucket,
  Confidence,
  ConfidenceReason,
  CoverageCell,
  IndicatorCell,
  NeedCategory,
  RankingCriterion,
  ServiceKind,
  StatusMix,
} from '../schema';
import { PARISH_AREAS, SECTOR_AREAS, SECTOR_SEEDS, TENANT } from './data';

export const METHOD_VERSION = 'rank-v1 (mock)';
export const NEED_CATEGORIES: NeedCategory[] = ['water_drinking', 'water_other', 'charging'];
export const SERVICES: ServiceKind[] = ['electricity', 'piped_water'];
export const BUCKET_HOURS: Record<Bucket, number> = { '6h': 6, '24h': 24, '7d': 168 };
const BUCKET_FACTOR: Record<Bucket, number> = { '6h': 0.3, '24h': 1, '7d': 2.5 };

export const RANKING_CRITERIA: RankingCriterion[] = [
  { key: 'urgent_active_needs', direction: 'desc' },
  { key: 'needs_per_reporter', direction: 'desc' },
  { key: 'oldest_unmet_need', direction: 'asc' },
  { key: 'freshness', direction: 'desc' },
];

const HOUR = 3600_000;

/** Raw (pre-suppression) values for one area × category × bucket. */
interface Raw {
  reporters: number;
  needs: number;
  peopleKnown: number;
  peopleUnknown: number;
  urgent: number;
  soon: number;
  canWait: number;
  urgencyUnknown: number;
  freshnessMs: number;
  oldestMs: number;
  pendingShare: number;
  external: 'agrees' | 'conflicts' | 'none';
}

function rawFor(sectorIdx: number, catIdx: number, bucket: Bucket, now: number): Raw | null {
  const seed = SECTOR_SEEDS[sectorIdx]!;
  const cat = NEED_CATEGORIES[catIdx]!;
  const intensity = seed.intensity[cat];
  if (intensity === 0) return null;
  const hours = BUCKET_HOURS[bucket];
  const reporters = Math.max(0, Math.round(intensity * 2.2 * BUCKET_FACTOR[bucket]));
  if (reporters === 0) return null;
  const needs = Math.round(reporters * (1.1 + ((sectorIdx + catIdx) % 3) * 0.15));
  const urgentShare = 0.12 + ((sectorIdx * 7 + catIdx * 3) % 5) * 0.07;
  const urgent = Math.round(needs * urgentShare);
  const urgencyUnknown = Math.round(needs * 0.1);
  const soon = Math.round((needs - urgent - urgencyUnknown) * 0.6);
  const canWait = Math.max(0, needs - urgent - urgencyUnknown - soon);
  const peopleUnknown = Math.round(needs * (0.05 + (sectorIdx % 3) * 0.05));
  const peopleKnown = (needs - peopleUnknown) * (3 + ((sectorIdx + catIdx) % 3));
  const freshHours = Math.min(hours * 0.9, ((sectorIdx * 5 + catIdx * 2) % 9) + 0.5);
  const oldestHours = Math.min(hours, 10 + ((sectorIdx * 13 + catIdx * 7) % 140));
  return {
    reporters,
    needs,
    peopleKnown,
    peopleUnknown,
    urgent,
    soon,
    canWait,
    urgencyUnknown,
    freshnessMs: now - freshHours * HOUR,
    oldestMs: now - Math.max(oldestHours, freshHours) * HOUR,
    pendingShare: ((sectorIdx + catIdx) % 4) * 0.1,
    external: seed.external,
  };
}

function sumRaw(raws: Raw[]): Raw | null {
  if (raws.length === 0) return null;
  const s = (f: (r: Raw) => number) => raws.reduce((a, r) => a + f(r), 0);
  const needs = s((r) => r.needs);
  return {
    reporters: s((r) => r.reporters),
    needs,
    peopleKnown: s((r) => r.peopleKnown),
    peopleUnknown: s((r) => r.peopleUnknown),
    urgent: s((r) => r.urgent),
    soon: s((r) => r.soon),
    canWait: s((r) => r.canWait),
    urgencyUnknown: s((r) => r.urgencyUnknown),
    freshnessMs: Math.max(...raws.map((r) => r.freshnessMs)),
    oldestMs: Math.min(...raws.map((r) => r.oldestMs)),
    pendingShare: s((r) => r.pendingShare * r.needs) / Math.max(needs, 1),
    external: raws.some((r) => r.external === 'conflicts')
      ? 'conflicts'
      : raws.some((r) => r.external === 'agrees')
        ? 'agrees'
        : 'none',
  };
}

function confidenceFor(raw: Raw | null, now: number): Confidence {
  if (!raw) return { level: 'low', reasons: ['single_source', 'no_external'] };
  const reasons: ConfidenceReason[] = [];
  let score = 0;
  if (raw.reporters >= 8) {
    reasons.push('multiple_sources');
    score += 1;
  } else reasons.push('single_source');
  if (raw.pendingShare < 0.2) {
    reasons.push('reviewed');
    score += 1;
  } else reasons.push('pending_review');
  if (now - raw.freshnessMs < 12 * HOUR) {
    reasons.push('fresh');
    score += 1;
  } else reasons.push('stale');
  if (raw.external === 'agrees') {
    reasons.push('agrees_external');
    score += 1;
  } else if (raw.external === 'conflicts') {
    reasons.push('conflicts_external');
    score -= 1;
  } else reasons.push('no_external');
  return { level: score >= 3 ? 'high' : score === 2 ? 'medium' : 'low', reasons };
}

function emptyCell(
  area: AreaRef,
  bucket: Bucket,
  now: number,
  category: NeedCategory | null,
  service: ServiceKind | null,
): IndicatorCell {
  return {
    area,
    category,
    service,
    bucket,
    suppressed: false,
    coverage_label: 'none',
    active_needs: null,
    distinct_reporters: null,
    distinct_households: null,
    people_affected_known: null,
    people_affected_unknown_count: null,
    urgency_mix: null,
    supply_mix: null,
    status_mix: null,
    freshness: null,
    pending_review_share: null,
    confidence: confidenceFor(null, now),
    method_version: METHOD_VERSION,
    input_watermark: new Date(now - 2 * 60_000).toISOString(),
  };
}

function needCell(area: AreaRef, cat: NeedCategory, bucket: Bucket, raw: Raw | null, now: number): IndicatorCell {
  const base = emptyCell(area, bucket, now, cat, null);
  if (!raw) return base;
  const confidence = confidenceFor(raw, now);
  if (raw.reporters < TENANT.k) {
    // DOM-044 / SEC-10: suppressed — only labels survive.
    return { ...base, suppressed: true, coverage_label: 'thin', confidence };
  }
  return {
    ...base,
    coverage_label: 'reported',
    active_needs: raw.needs,
    distinct_reporters: raw.reporters,
    people_affected_known: raw.peopleKnown,
    people_affected_unknown_count: raw.peopleUnknown,
    urgency_mix: { urgent: raw.urgent, soon: raw.soon, can_wait: raw.canWait, unknown: raw.urgencyUnknown },
    supply_mix: {
      none: Math.round(raw.needs * 0.3),
      under_one_day: Math.round(raw.needs * 0.3),
      one_to_three_days: Math.round(raw.needs * 0.2),
      more_than_three_days: Math.round(raw.needs * 0.1),
      unknown: raw.needs - Math.round(raw.needs * 0.3) * 2 - Math.round(raw.needs * 0.2) - Math.round(raw.needs * 0.1),
    },
    freshness: new Date(raw.freshnessMs).toISOString(),
    pending_review_share: Math.round(raw.pendingShare * 100) / 100,
    confidence,
  };
}

function serviceCell(area: AreaRef, service: ServiceKind, bucket: Bucket, raws: Raw[], now: number): IndicatorCell {
  const base = emptyCell(area, bucket, now, null, service);
  const raw = sumRaw(raws);
  if (!raw) return base;
  const confidence = confidenceFor(raw, now);
  if (raw.reporters < TENANT.k) return { ...base, suppressed: true, coverage_label: 'thin', confidence };
  const offShare = service === 'electricity' ? 0.55 : 0.7;
  const off = Math.round(raw.reporters * offShare);
  const intermittent = Math.round(raw.reporters * 0.2);
  const unknown = Math.round(raw.reporters * 0.05);
  const status_mix: StatusMix = { off, intermittent, unknown, on: Math.max(0, raw.reporters - off - intermittent - unknown) };
  return {
    ...base,
    coverage_label: 'reported',
    distinct_reporters: raw.reporters,
    status_mix,
    freshness: new Date(raw.freshnessMs).toISOString(),
    pending_review_share: Math.round(raw.pendingShare * 100) / 100,
    confidence,
  };
}

function sectorIndex(id: string) {
  return SECTOR_SEEDS.findIndex((s) => s.id === id);
}

function rawForArea(area: AreaRef, catIdx: number, bucket: Bucket, now: number): Raw | null {
  if (area.level === 'sector') return rawFor(sectorIndex(area.id), catIdx, bucket, now);
  // Parish: merged from its sectors before suppression (DOM-044 merge up).
  const raws = SECTOR_AREAS.filter((s) => s.parent_id === area.id)
    .map((s) => rawFor(sectorIndex(s.id), catIdx, bucket, now))
    .filter((r): r is Raw => r !== null);
  return sumRaw(raws);
}

export function areasAt(level: 'parish' | 'sector'): AreaRef[] {
  return level === 'parish' ? PARISH_AREAS : SECTOR_AREAS;
}

export function needCells(level: 'parish' | 'sector', bucket: Bucket, now: number, category?: NeedCategory): IndicatorCell[] {
  const cats = category ? [category] : NEED_CATEGORIES;
  return areasAt(level).flatMap((area) =>
    cats.map((cat) => needCell(area, cat, bucket, rawForArea(area, NEED_CATEGORIES.indexOf(cat), bucket, now), now)),
  );
}

export function serviceCells(level: 'parish' | 'sector', bucket: Bucket, now: number, service?: ServiceKind): IndicatorCell[] {
  const services = service ? [service] : SERVICES;
  return areasAt(level).flatMap((area) =>
    services.map((svc) => {
      // Synthetic: piped water outages track water needs; electricity tracks charging.
      const cats = svc === 'piped_water' ? [0, 1] : [2];
      const raws = cats.map((c) => rawForArea(area, c, bucket, now)).filter((r): r is Raw => r !== null);
      return serviceCell(area, svc, bucket, raws, now);
    }),
  );
}

export function rankAreas(cells: IndicatorCell[]): { items: AreaOfNeed[]; unranked: IndicatorCell[] } {
  const rankable = cells.filter((c) => !c.suppressed && c.coverage_label === 'reported');
  const unranked = cells.filter((c) => !rankable.includes(c));
  const values = (c: IndicatorCell) => ({
    urgent_active_needs: c.urgency_mix!.urgent,
    needs_per_reporter: Math.round((c.active_needs! / c.distinct_reporters!) * 100) / 100,
    // Synthetic stand-in for the oldest unmet need: derived from freshness.
    oldest_unmet_need: new Date(Date.parse(c.freshness!) - (c.active_needs! % 7) * 6 * HOUR).toISOString(),
    freshness: c.freshness!,
  });
  const sorted = rankable
    .map((c) => ({ cell: c, v: values(c) }))
    .sort(
      (a, b) =>
        b.v.urgent_active_needs - a.v.urgent_active_needs ||
        b.v.needs_per_reporter - a.v.needs_per_reporter ||
        Date.parse(a.v.oldest_unmet_need) - Date.parse(b.v.oldest_unmet_need) ||
        Date.parse(b.v.freshness) - Date.parse(a.v.freshness),
    );
  return {
    items: sorted.map((x, i) => ({ rank: i + 1, cell: x.cell, criteria_values: x.v })),
    unranked,
  };
}

export const HIGH_NEED_THRESHOLD = { active_needs: 20, urgent: 5 };

export function coverageCells(
  bucket: Bucket,
  now: number,
  activities: Activity[],
  category?: NeedCategory,
): CoverageCell[] {
  return needCells('sector', bucket, now, category).map((need) => {
    const serving = activities.filter(
      (a) =>
        a.category === need.category &&
        a.status === 'active' &&
        a.areas.some((ar) => ar.id === need.area.id),
    );
    const high_need =
      !need.suppressed &&
      need.coverage_label === 'reported' &&
      ((need.active_needs ?? 0) >= HIGH_NEED_THRESHOLD.active_needs ||
        (need.urgency_mix?.urgent ?? 0) >= HIGH_NEED_THRESHOLD.urgent);
    const status: CoverageCell['status'] =
      serving.length > 0 ? 'covered' : need.coverage_label === 'none' ? 'unknown' : 'uncovered';
    return {
      area: need.area,
      category: need.category!,
      status,
      high_need,
      need,
      activities: serving.map(({ id, provider_organization, type, status: st, details_hidden }) => ({
        id,
        provider_organization,
        type,
        status: st,
        details_hidden,
      })),
    };
  });
}
