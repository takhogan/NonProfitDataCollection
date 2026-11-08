import { Link } from 'react-router';
import type { AreaOfNeed, CoverageCell, IndicatorCell } from '../../api';
import { useAreasOfNeed, useCoverage } from '../../api/queries';
import { useI18n } from '../../locales/i18n';
import { commonStyles, CoverageStatusBadge, Loading, QueryError } from '../../ui/common';
import {
  CellCount,
  ConfidenceBadge,
  CoverageLabelBadge,
  Freshness,
  Insufficient,
  NoData,
  PeopleAffected,
  UrgencyMixView,
} from '../../ui/honest';
import tableStyles from '../../ui/table.module.css';
import { ExportButton } from '../exports/ExportButton';
import { areasOfNeedCsv } from '../exports/csv';
import { BucketSelect, CategorySelect, LevelSelect, useAggregateFilters } from '../filters';
import { RankingCriteria } from './RankingCriteria';

/** WEB-010 */
export default function AreasOfNeedPage() {
  const { t, lang } = useI18n();
  const { bucket, category, level, set } = useAggregateFilters();
  const q = useAreasOfNeed({ bucket, category, level });
  // Provider coverage is computed per sector (DOM-052).
  const cov = useCoverage({ bucket, category }, level === 'sector');
  const covKey = (c: { area: { id: string }; category: string | null }) => `${c.area.id}|${c.category}`;
  const covByCell = new Map<string, CoverageCell>((cov.data?.items ?? []).map((c) => [covKey(c), c]));

  return (
    <>
      <div className={commonStyles.headerRow}>
        <h1>{t('areas.title')}</h1>
        {q.data && (
          <ExportButton
            filename={`areas-de-necesidad-${bucket}`}
            build={() => areasOfNeedCsv(q.data, lang)}
          />
        )}
      </div>
      <form className={commonStyles.filters} onSubmit={(e) => e.preventDefault()} aria-label={t('filters.label')}>
        <CategorySelect value={category} onChange={(c) => set('category', c)} />
        <BucketSelect value={bucket} onChange={(b) => set('bucket', b)} />
        <LevelSelect value={level} onChange={(l) => set('level', l === 'sector' ? undefined : l)} />
      </form>

      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <QueryError error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          <RankingCriteria criteria={q.data.criteria} methodVersion={q.data.method_version} />
          <div className={tableStyles.wrap}>
            <table className={tableStyles.table}>
              <caption>
                {t('areas.tableCaption', { bucket: t(`bucket.${q.data.bucket}`), count: q.data.items.length })}
              </caption>
              <thead>
                <tr>
                  <th scope="col">{t('areas.col.rank')}</th>
                  <th scope="col">{t('areas.col.area')}</th>
                  <th scope="col">{t('areas.col.activeNeeds')}</th>
                  <th scope="col">{t('areas.col.reporters')}</th>
                  <th scope="col">{t('areas.col.people')}</th>
                  <th scope="col">{t('areas.col.urgency')}</th>
                  <th scope="col">{t('areas.col.coverage')}</th>
                  <th scope="col">{t('areas.col.freshness')}</th>
                  <th scope="col">{t('areas.col.confidence')}</th>
                </tr>
              </thead>
              <tbody>
                {q.data.items.map((row) => (
                  <RankedRow key={covKey(row.cell)} row={row} coverage={covByCell.get(covKey(row.cell))} />
                ))}
              </tbody>
            </table>
          </div>
          {q.data.items.length === 0 && <p>{t('areas.noneRanked')}</p>}

          {q.data.unranked.length > 0 && (
            <>
              <h2>{t('areas.unrankedTitle')}</h2>
              <p className="muted">{t('areas.unrankedHelp')}</p>
              <ul>
                {q.data.unranked.map((c) => (
                  <UnrankedItem key={covKey(c)} cell={c} />
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </>
  );
}

function AreaName({ cell }: { cell: IndicatorCell }) {
  const { t } = useI18n();
  return (
    <>
      <Link to={`/areas/${cell.area.id}`}>{cell.area.name}</Link>
      {cell.area.parent_name && <span className="muted"> · {cell.area.parent_name}</span>}
      {cell.category && (
        <div style={{ fontSize: '0.875rem' }}>{t(`category.${cell.category}`)}</div>
      )}
    </>
  );
}

function RankedRow({ row, coverage }: { row: AreaOfNeed; coverage?: CoverageCell }) {
  const { t } = useI18n();
  const { cell } = row;
  const highlight = coverage?.status === 'uncovered' && coverage.high_need;
  return (
    <tr className={highlight ? tableStyles.highlight : undefined}>
      <td data-label={t('areas.col.rank')}>
        <strong>#{row.rank}</strong>
      </td>
      <th scope="row" data-label={t('areas.col.area')} style={{ fontWeight: 'normal' }}>
        <AreaName cell={cell} />
      </th>
      <td data-label={t('areas.col.activeNeeds')}>
        <CellCount cell={cell} field="active_needs" />
      </td>
      <td data-label={t('areas.col.reporters')}>
        <CellCount cell={cell} field="distinct_reporters" />
      </td>
      <td data-label={t('areas.col.people')}>
        <PeopleAffected cell={cell} />
      </td>
      <td data-label={t('areas.col.urgency')}>
        <UrgencyMixView mix={cell.urgency_mix} />
      </td>
      <td data-label={t('areas.col.coverage')}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
          {coverage && <CoverageStatusBadge status={coverage.status} highNeed={coverage.high_need} />}
          <CoverageLabelBadge label={cell.coverage_label} />
        </div>
      </td>
      <td data-label={t('areas.col.freshness')}>
        <Freshness iso={cell.freshness} />
      </td>
      <td data-label={t('areas.col.confidence')}>
        <ConfidenceBadge confidence={cell.confidence} />
      </td>
    </tr>
  );
}

function UnrankedItem({ cell }: { cell: IndicatorCell }) {
  const { t } = useI18n();
  return (
    <li style={{ marginBottom: '0.35rem' }}>
      <Link to={`/areas/${cell.area.id}`}>{cell.area.name}</Link>
      {cell.area.parent_name && <span className="muted"> · {cell.area.parent_name}</span>} —{' '}
      {cell.category && t(`category.${cell.category}`)}: {cell.suppressed ? <Insufficient /> : <NoData />}
    </li>
  );
}
