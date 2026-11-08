import { Link, useParams, useSearchParams } from 'react-router';
import type { Activity, Bucket, ExternalSignal, HistoryPoint, IndicatorCell } from '../../api';
import { useAreaDetail } from '../../api/queries';
import { formatDate, formatDateTime } from '../../locales/format';
import { useI18n } from '../../locales/i18n';
import { commonStyles, Loading, QueryError } from '../../ui/common';
import {
  CellCount,
  CellMeta,
  Count,
  Insufficient,
  NoData,
  PeopleAffected,
  StatusMixView,
  UrgencyMixView,
} from '../../ui/honest';
import tableStyles from '../../ui/table.module.css';
import { formatQuantity, formatSchedule } from '../activities/schedule';
import { BucketSelect, CATEGORIES } from '../filters';

/** WEB-013 */
export default function AreaDetailPage() {
  const { areaId = '' } = useParams();
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const bucket = (['6h', '24h', '7d'].includes(params.get('bucket') ?? '') ? params.get('bucket') : '24h') as Bucket;
  const q = useAreaDetail(areaId);

  if (q.isPending) return <Loading />;
  if (q.isError) return <QueryError error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  const needs = d.needs.filter((c) => c.bucket === bucket);
  const services = d.services.filter((c) => c.bucket === bucket);

  return (
    <>
      <p style={{ margin: 0 }}>
        <Link to="/areas">← {t('nav.areasOfNeed')}</Link>
      </p>
      <h1>
        {d.area.name}{' '}
        <span className="muted" style={{ fontSize: '1rem', fontWeight: 'normal' }}>
          {t(`level.${d.area.level}`)}
          {d.area.parent_name ? ` · ${d.area.parent_name}` : ''}
        </span>
      </h1>
      {d.area.aliases.length > 0 && (
        <p className="muted">{t('area.aliases', { aliases: d.area.aliases.join(', ') })}</p>
      )}

      <form className={commonStyles.filters} onSubmit={(e) => e.preventDefault()}>
        <BucketSelect value={bucket} onChange={(b) => setParams({ bucket: b }, { replace: true })} />
      </form>

      <h2>{t('area.needsTitle')}</h2>
      <table className={tableStyles.table}>
        <thead>
          <tr>
            <th scope="col">{t('filters.category')}</th>
            <th scope="col">{t('areas.col.activeNeeds')}</th>
            <th scope="col">{t('areas.col.reporters')}</th>
            <th scope="col">{t('areas.col.people')}</th>
            <th scope="col">{t('areas.col.urgency')}</th>
            <th scope="col">{t('coverage.col.data')}</th>
          </tr>
        </thead>
        <tbody>
          {needs.map((c) => (
            <NeedRow key={c.category} cell={c} />
          ))}
        </tbody>
      </table>

      <h2>{t('area.servicesTitle')}</h2>
      <table className={tableStyles.table}>
        <thead>
          <tr>
            <th scope="col">{t('area.service')}</th>
            <th scope="col">{t('area.statusMix')}</th>
            <th scope="col">{t('coverage.col.data')}</th>
          </tr>
        </thead>
        <tbody>
          {services.map((c) => (
            <ServiceRow key={c.service} cell={c} />
          ))}
        </tbody>
      </table>

      <h2>{t('area.historyTitle')}</h2>
      <HistoryTable history={d.history} />

      <h2>{t('area.activitiesTitle')}</h2>
      {d.activities.length === 0 ? (
        <p>{t('area.noActivities')}</p>
      ) : (
        <ul>
          {d.activities.map((a) => (
            <ActivityLine key={a.id} activity={a} />
          ))}
        </ul>
      )}
      <p>
        <Link to={`/activities/new?area=${d.area.level === 'sector' ? d.area.id : ''}`}>{t('nav.logActivity')}</Link>
      </p>

      <h2>{t('area.meetingPointsTitle')}</h2>
      {d.meeting_points.length === 0 ? (
        <p className="muted">{t('area.noMeetingPoints')}</p>
      ) : (
        <ul>
          {d.meeting_points.map((m) => (
            <li key={m.id}>
              {m.name} <span className="muted">({t(`meetingPointKind.${m.kind}`)})</span>
            </li>
          ))}
        </ul>
      )}

      <section aria-labelledby="external-title" className={commonStyles.notice}>
        <h2 id="external-title" style={{ marginTop: 0 }}>
          {t('area.externalTitle')}
        </h2>
        <p className="muted" style={{ marginTop: 0 }}>
          {t('area.externalExplainer')}
        </p>
        <ExternalContext signals={d.external_context} />
      </section>

      <h2>{t('area.qualityTitle')}</h2>
      {d.data_quality.length === 0 ? (
        <p>{t('area.qualityNone')}</p>
      ) : (
        <ul>
          {d.data_quality.map((n) => (
            <li key={n.code}>{t(`quality.${n.code}`)}</li>
          ))}
        </ul>
      )}
      <p className="muted" style={{ fontSize: '0.85rem' }}>
        {t('ranking.method', { version: d.method_version })}
      </p>
    </>
  );
}

function NeedRow({ cell }: { cell: IndicatorCell }) {
  const { t } = useI18n();
  return (
    <tr>
      <th scope="row" data-label={t('filters.category')} style={{ fontWeight: 'normal' }}>
        {cell.category && t(`category.${cell.category}`)}
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
        {cell.urgency_mix ? <UrgencyMixView mix={cell.urgency_mix} /> : <span className="muted">—</span>}
      </td>
      <td data-label={t('coverage.col.data')}>
        <CellMeta cell={cell} showBucket={false} />
      </td>
    </tr>
  );
}

function ServiceRow({ cell }: { cell: IndicatorCell }) {
  const { t } = useI18n();
  return (
    <tr>
      <th scope="row" data-label={t('area.service')} style={{ fontWeight: 'normal' }}>
        {cell.service && t(`service.${cell.service}`)}
      </th>
      <td data-label={t('area.statusMix')}>
        {cell.coverage_label === 'none' ? <NoData /> : cell.suppressed ? <Insufficient /> : <StatusMixView mix={cell.status_mix} />}
      </td>
      <td data-label={t('coverage.col.data')}>
        <CellMeta cell={cell} showBucket={false} />
      </td>
    </tr>
  );
}

function HistoryTable({ history }: { history: HistoryPoint[] }) {
  const { t, locale } = useI18n();
  const dates = [...new Set(history.map((h) => h.date))];
  const at = (date: string, cat: string) => history.find((h) => h.date === date && h.category === cat);
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className={tableStyles.table} style={{ minWidth: 0 }}>
        <caption>{t('area.historyCaption')}</caption>
        <thead>
          <tr>
            <th scope="col">{t('area.date')}</th>
            {CATEGORIES.map((c) => (
              <th scope="col" key={c}>
                {t(`category.${c}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dates.map((date) => (
            <tr key={date}>
              <th scope="row" data-label={t('area.date')} style={{ fontWeight: 'normal' }}>
                {formatDate(date, locale)}
              </th>
              {CATEGORIES.map((c) => {
                const p = at(date, c);
                return (
                  <td key={c} data-label={t(`category.${c}`)}>
                    {!p || (p.active_needs === null && !p.suppressed) ? (
                      <NoData />
                    ) : p.suppressed ? (
                      <Insufficient />
                    ) : (
                      <Count value={p.active_needs!} unit="needs" />
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ActivityLine({ activity: a }: { activity: Activity }) {
  const { t, lang } = useI18n();
  return (
    <li style={{ marginBottom: '0.4rem' }}>
      <strong>{a.provider_organization.name}</strong> —{' '}
      {a.details_hidden ? (
        <span className="muted">{t('activity.detailsHidden')}</span>
      ) : (
        <>
          {t(`activityType.${a.type}`)}, {t(`category.${a.category}`)}
          {a.schedule && <> · {formatSchedule(a.schedule, lang)}</>}
          {a.capacity && <> · {formatQuantity(a.capacity, lang)}</>}
          {a.public_location && <> · {a.public_location.name}</>}
        </>
      )}{' '}
      <span className="muted">({t(`activityStatus.${a.status}`)})</span>
      {a.unconfirmed && <span className="muted"> · {t('activity.unconfirmedShort')}</span>}
    </li>
  );
}

function ExternalContext({ signals }: { signals: ExternalSignal[] }) {
  const { t, locale } = useI18n();
  if (signals.length === 0) return <p style={{ margin: 0 }}>{t('area.externalNone')}</p>;
  return (
    <ul style={{ margin: 0 }}>
      {signals.map((s) => (
        <li key={`${s.source}-${s.observed_at}`}>
          <strong>{t(`externalSource.${s.source}`)}</strong>: {t(`externalKind.${s.kind}`)} ·{' '}
          <time dateTime={s.observed_at}>{formatDateTime(s.observed_at, locale)}</time>
        </li>
      ))}
    </ul>
  );
}
