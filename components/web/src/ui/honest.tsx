/**
 * WEB-004 "honest numbers": every number carries its unit, bucket, freshness,
 * coverage label and confidence (with reasons). Suppressed cells read "datos
 * insuficientes"; cells with no data read "sin datos" — never zero.
 */
import type { Bucket, Confidence, CoverageLabel, IndicatorCell, StatusMix, UrgencyMix } from '../api';
import { useI18n } from '../locales/i18n';
import { formatDateTime, formatRelative } from '../locales/format';
import s from './honest.module.css';

export function NoData() {
  const { t } = useI18n();
  return <span className={s.unknown}>{t('honest.noData')}</span>;
}

export function Insufficient() {
  const { t } = useI18n();
  return (
    <span className={s.suppressed} title={t('honest.insufficientHint')}>
      {t('honest.insufficient')}
    </span>
  );
}

/** Returns a placeholder when the cell cannot show numbers, else null. */
export function cellGate(cell: IndicatorCell) {
  if (cell.coverage_label === 'none') return <NoData />;
  if (cell.suppressed) return <Insufficient />;
  return null;
}

type Unit = 'needs' | 'reporters' | 'households' | 'people';

export function Count({ value, unit }: { value: number; unit: Unit }) {
  const { t } = useI18n();
  return (
    <span>
      <span className={s.value}>{t('number', { n: value })}</span>{' '}
      <span className={s.unit}>{t(`unit.${unit}`, { count: value })}</span>
    </span>
  );
}

export function CellCount({ cell, field }: { cell: IndicatorCell; field: 'active_needs' | 'distinct_reporters' | 'distinct_households' }) {
  const gate = cellGate(cell);
  if (gate) return gate;
  const v = cell[field];
  if (v === null) return <NoData />;
  const unit: Unit = field === 'active_needs' ? 'needs' : field === 'distinct_reporters' ? 'reporters' : 'households';
  return <Count value={v} unit={unit} />;
}

export function PeopleAffected({ cell }: { cell: IndicatorCell }) {
  const { t } = useI18n();
  const gate = cellGate(cell);
  if (gate) return gate;
  const known = cell.people_affected_known ?? 0;
  const unknown = cell.people_affected_unknown_count ?? 0;
  return (
    <span>
      <Count value={known} unit="people" />
      {unknown > 0 && <span className={s.unit}> {t('honest.peopleUnknown', { count: unknown })}</span>}
    </span>
  );
}

export function UrgencyMixView({ mix }: { mix: UrgencyMix | null }) {
  const { t } = useI18n();
  if (!mix) return <NoData />;
  return (
    <span className={s.mix}>
      <span className={`${s.mixPart} ${mix.urgent > 0 ? s.urgent : ''}`}>
        {t('urgency.urgent')} {t('number', { n: mix.urgent })}
      </span>
      {' · '}
      <span className={s.mixPart}>
        {t('urgency.soon')} {t('number', { n: mix.soon })}
      </span>
      {' · '}
      <span className={s.mixPart}>
        {t('urgency.can_wait')} {t('number', { n: mix.can_wait })}
      </span>
      {mix.unknown > 0 && (
        <>
          {' · '}
          <span className={s.mixPart}>
            {t('urgency.unknown')} {t('number', { n: mix.unknown })}
          </span>
        </>
      )}
    </span>
  );
}

export function StatusMixView({ mix }: { mix: StatusMix | null }) {
  const { t } = useI18n();
  if (!mix) return <NoData />;
  const parts: [keyof StatusMix, number][] = [
    ['off', mix.off],
    ['intermittent', mix.intermittent],
    ['on', mix.on],
    ['unknown', mix.unknown],
  ];
  return (
    <span className={s.mix}>
      {parts.map(([k, v], i) => (
        <span key={k}>
          {i > 0 && ' · '}
          {t(`status.${k}`)} {t('number', { n: v })}
        </span>
      ))}{' '}
      <span className={s.unit}>({t('unit.reporters', { count: mix.off + mix.on + mix.intermittent + mix.unknown })})</span>
    </span>
  );
}

export function Freshness({ iso, approximate }: { iso: string | null; approximate?: boolean }) {
  const { t, locale } = useI18n();
  if (!iso) return <NoData />;
  return (
    <time dateTime={iso} title={formatDateTime(iso, locale, { approximate })}>
      {t('honest.updated', { when: formatRelative(iso, locale) })}
    </time>
  );
}

export function BucketLabel({ bucket }: { bucket: Bucket }) {
  const { t } = useI18n();
  return <span>{t(`bucket.${bucket}`)}</span>;
}

export function CoverageLabelBadge({ label }: { label: CoverageLabel }) {
  const { t } = useI18n();
  return (
    <span className={`${s.badge} ${label === 'reported' ? '' : s.low}`} title={t(`coverageLabel.${label}.hint`)}>
      {t(`coverageLabel.${label}`)}
    </span>
  );
}

/** Native <details> so the reasons open on tap and on keyboard, not just hover. */
export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const { t } = useI18n();
  const reasons = confidence.reasons.map((r) => t(`confidenceReason.${r}`));
  return (
    <details className={s.confidence}>
      <summary title={reasons.join('; ')}>
        <span className={`${s.badge} ${s[confidence.level]}`}>
          {t(`confidence.${confidence.level}`)} <span aria-hidden="true">ⓘ</span>
        </span>
      </summary>
      <ul className={s.reasons} aria-label={t('confidence.reasonsLabel')}>
        {reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </details>
  );
}

/** One line with the bucket, freshness, coverage label and confidence of a cell. */
export function CellMeta({ cell, showBucket = true }: { cell: IndicatorCell; showBucket?: boolean }) {
  return (
    <span className={s.meta}>
      {showBucket && <BucketLabel bucket={cell.bucket} />}
      {cell.freshness && <Freshness iso={cell.freshness} />}
      <CoverageLabelBadge label={cell.coverage_label} />
      <ConfidenceBadge confidence={cell.confidence} />
    </span>
  );
}
