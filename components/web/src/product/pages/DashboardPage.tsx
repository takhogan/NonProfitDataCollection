import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useI18n } from '../../locales/i18n';
import { formatDateTime, formatRelative } from '../../locales/format';
import { Grid, Stat, Tag } from '../../ui/kit';
import { Segmented } from '../../ui/Segmented';
import { useDashboardSummary } from '../../api/product/queries';
import { useT } from '../i18n';
import { useLiveFeed } from '../components/useLiveFeed';
import { useDashboardData, type AreaRollup, type TimeRange } from '../components/useDashboardData';
import { UrgentPill, useChannelLabel, useLabels } from '../components/bits';
import { AskBar } from '../components/AskBar';
import s from './Dashboard.module.css';

export default function DashboardPage() {
  const t = useT();
  const { locale } = useI18n();
  const navigate = useNavigate();
  const [range, setRange] = useState<TimeRange>('today');

  const summary = useDashboardSummary();
  const { data: roll } = useDashboardData(range);
  const { items: feed, newIds } = useLiveFeed(5000, 40, range);
  const channelLabel = useChannelLabel();
  const L = useLabels();

  const m = roll?.metrics;
  const maxReports = Math.max(1, ...(roll?.areas ?? []).map((a) => a.reports));

  const rangeOptions = [
    { value: 'today' as const, label: t('dashboard.range.today') },
    { value: '7d' as const, label: t('dashboard.range.7d') },
    { value: 'all' as const, label: t('dashboard.range.all') },
  ];

  return (
    <>
      <h1 className={s.pageTitle}>{t('dashboard.title')}</h1>

      {/* AI summary — opens the page, serif, with an Updated line */}
      <div className={s.summary}>
        <p className={s.summaryText}>
          {summary.isPending ? t('common.loading') : summary.data?.summary}
        </p>
        {summary.data && (
          <p className={s.summaryMeta}>
            {t('dashboard.updated')} {formatDateTime(summary.data.generated_at, locale)}
          </p>
        )}
      </div>

      <div className={s.rangeRow}>
        <Segmented options={rangeOptions} value={range} onChange={setRange} ariaLabel={t('dashboard.summaryTitle')} />
      </div>

      {/* Metric cards */}
      <Grid cols={4} style={{ marginTop: '0.25rem' }}>
        <MetricCard value={m?.reports} label={t('dashboard.metric.reports_today')} />
        <MetricCard value={m?.withoutPower} label={t('dashboard.metric.without_power')} />
        <MetricCard value={m?.withoutWater} label={t('dashboard.metric.without_water')} />
        <MetricCard value={m?.urgent} label={t('dashboard.metric.urgent')} danger />
      </Grid>

      <div className={s.layout}>
        {/* Hero: neighborhoods */}
        <section className={s.hero}>
          <h2 className={s.heroTitle}>{t('dashboard.areas')}</h2>
          <div className={s.areaList}>
            {(roll?.areas ?? []).map((a) => (
              <AreaRow
                key={a.area}
                a={a}
                maxReports={maxReports}
                locale={locale}
                labels={{ reports: t('dashboard.area.reports'), noPower: t('dashboard.noPower'), noWater: t('dashboard.noWater'), both: t('dashboard.both') }}
                onClick={() => navigate(`/app/data?area=${encodeURIComponent(a.area)}`)}
              />
            ))}
            {roll && roll.areas.length === 0 && <p className="muted">{t('reports.empty')}</p>}
          </div>
        </section>

        {/* Right rail: urgent + compact feed */}
        <aside className={s.rail}>
          <section>
            <h2 className={s.railTitle}>{t('dashboard.urgent')}</h2>
            {roll && roll.urgent.length === 0 ? (
              <p className="muted">{t('dashboard.urgentEmpty')}</p>
            ) : (
              <div className={s.urgentList}>
                {(roll?.urgent ?? []).map((r) => (
                  <Link key={r.id} to={`/app/reports/${r.id}`} className={s.urgentItem}>
                    <span className={s.urgentBody}>
                      <span className={s.urgentArea}>{r.area}</span>
                      <span className={s.urgentTags}>{(r.tags ?? []).slice(0, 2).map(L.tag).join(' · ')}</span>
                    </span>
                    <UrgentPill />
                  </Link>
                ))}
              </div>
            )}
          </section>

          <section>
            <div className={s.railHead}>
              <h2 className={s.railTitle}>{t('dashboard.feed')}</h2>
              <Link to="/app/data" className={s.viewAll}>{t('dashboard.viewAll')}</Link>
            </div>
            {feed.length === 0 ? (
              <p className="muted">{t('dashboard.feedEmpty')}</p>
            ) : (
              <div className={s.feed}>
                {feed.map((item) => {
                  const inner = (
                    <>
                      <div className={s.msgTop}>
                        <span className={s.msgArea}>
                          {item.area} · <span className={s.chan}>{channelLabel(item.channel)}</span>
                        </span>
                        <span className={s.msgTime}>{formatRelative(item.received_at, locale)}</span>
                      </div>
                      <p className={s.msgText}>{item.preview}</p>
                      {item.tags.length > 0 && (
                        <div className={s.msgTags}>
                          {item.tags.slice(0, 2).map((tag) => (
                            <Tag key={tag}>{L.tag(tag)}</Tag>
                          ))}
                        </div>
                      )}
                    </>
                  );
                  const cls = `${s.msg} ${newIds.has(item.id) ? s.msgNew : ''}`;
                  return item.report_id ? (
                    <Link key={item.id} to={`/app/reports/${item.report_id}`} className={cls}>{inner}</Link>
                  ) : (
                    <div key={item.id} className={cls}>{inner}</div>
                  );
                })}
              </div>
            )}
          </section>
        </aside>
      </div>

      <AskBar />
    </>
  );
}

function MetricCard({ value, label, danger }: { value: number | undefined; label: string; danger?: boolean }) {
  return (
    <div className={s.metric}>
      <Stat value={value ?? '—'} label={label} tone={danger ? 'danger' : undefined} />
    </div>
  );
}

function AreaRow({
  a,
  maxReports,
  locale,
  labels,
  onClick,
}: {
  a: AreaRollup;
  maxReports: number;
  locale: string;
  labels: { reports: string; noPower: string; noWater: string; both: string };
  onClick: () => void;
}) {
  const total = Math.max(1, a.reports);
  // Stacked bar: no-power-only, no-water-only, both. Scale group width by share of the busiest area.
  const scale = (a.reports / maxReports) * 100;
  const powerOnly = a.withoutPower - a.both;
  const waterOnly = a.withoutWater - a.both;
  const seg = (n: number) => `${(n / total) * scale}%`;

  return (
    <button type="button" className={s.areaRow} onClick={onClick}>
      <div className={s.areaTop}>
        <span className={s.areaName}>{a.area}</span>
        <span className={s.areaRight}>
          {a.urgent > 0 && <span className={`${s.areaUrgent} tnum`}>{a.urgent} {labels.reports === 'reportes' ? 'urg.' : 'urg.'}</span>}
          <span className={`${s.areaCount} tnum`}>{a.reports} {labels.reports}</span>
        </span>
      </div>
      <div className={s.barWrap} aria-hidden>
        <span className={`${s.bar} ${s.barPower}`} style={{ width: seg(powerOnly) }} />
        <span className={`${s.bar} ${s.barBoth}`} style={{ width: seg(a.both) }} />
        <span className={`${s.bar} ${s.barWater}`} style={{ width: seg(waterOnly) }} />
      </div>
      <div className={s.areaMeta}>
        <span className="tnum"><span className={`${s.dot} ${s.dotPower}`} />{a.withoutPower} {labels.noPower}</span>
        <span className="tnum"><span className={`${s.dot} ${s.dotWater}`} />{a.withoutWater} {labels.noWater}</span>
        {a.both > 0 && <span className="tnum"><span className={`${s.dot} ${s.dotBoth}`} />{a.both} {labels.both}</span>}
        <span className={s.areaLatest}>{formatRelative(a.latest, locale)}</span>
      </div>
    </button>
  );
}
