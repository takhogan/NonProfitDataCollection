import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useI18n } from '../../locales/i18n';
import { formatDateTime } from '../../locales/format';
import { Grid, LiveDot, Stat, Tag } from '../../ui/kit';
import {
  useAsk,
  useDashboardAreas,
  useDashboardSummary,
  useReports,
} from '../../api/product/queries';
import { useT } from '../i18n';
import { PrivacyBadge } from '../components/PrivacyBadge';
import { useLiveFeed } from '../components/useLiveFeed';
import { Ago, UrgentPill, useChannelLabel } from '../components/bits';
import type { AreaCount } from '../../api/product';
import s from './Dashboard.module.css';

export default function DashboardPage() {
  const t = useT();
  const { locale } = useI18n();
  const navigate = useNavigate();
  const summary = useDashboardSummary();
  const areas = useDashboardAreas();
  const reports = useReports();
  const { items: feed, newIds } = useLiveFeed();
  const channelLabel = useChannelLabel();

  const urgent = (reports.data ?? []).filter((r) => r.urgent);

  return (
    <>
      <div className={s.topbar}>
        <div>
          <h1 className={s.title}>{t('dashboard.title')}</h1>
          <div className={s.subline}>
            <LiveDot label={t('dashboard.listening')} />
            <span className={s.subDot}>·</span>
            <PrivacyBadge />
          </div>
        </div>
        <button type="button" onClick={() => navigate('/app/campaigns')}>
          {t('dashboard.collect')}
        </button>
      </div>

      {/* AI summary — the one serif accent */}
      <div className={s.summary}>
        <p className={s.summaryMeta}>
          {t('dashboard.summaryTitle')}
          {summary.data && (
            <>
              {' · '}
              {t('dashboard.updated')} {formatDateTime(summary.data.generated_at, locale)}
            </>
          )}
        </p>
        <p className={s.summaryText}>
          {summary.isPending ? t('common.loading') : summary.data?.summary}
        </p>
      </div>

      {/* Metric cards — big number + label, tabular figures, no icons */}
      <Grid cols={4} style={{ marginTop: '1.75rem' }}>
        <div className={s.metric}>
          <Stat value={summary.data?.metrics.reports_today ?? '—'} label={t('dashboard.metric.reports_today')} />
        </div>
        <div className={s.metric}>
          <Stat value={summary.data?.metrics.without_power ?? '—'} label={t('dashboard.metric.without_power')} />
        </div>
        <div className={s.metric}>
          <Stat value={summary.data?.metrics.without_water ?? '—'} label={t('dashboard.metric.without_water')} />
        </div>
        <div className={s.metric}>
          <Stat value={summary.data?.metrics.urgent ?? '—'} label={t('dashboard.metric.urgent')} tone="danger" />
        </div>
      </Grid>

      <div className={s.layout}>
        {/* Left: live feed */}
        <div className={s.col}>
          <section>
            <div className={s.sectionHead}>
              <h2>{t('dashboard.feed')}</h2>
              <LiveDot label={t('dashboard.listening')} />
            </div>
            {feed.length === 0 ? (
              <p className="muted">{t('dashboard.feedEmpty')}</p>
            ) : (
              <div className={s.feed}>
                {feed.map((m) => {
                  const inner = (
                    <>
                      <div className={s.msgTop}>
                        <span>
                          {m.area} · <span className={s.chanTag}>{channelLabel(m.channel)}</span>
                        </span>
                        <Ago at={m.received_at} />
                      </div>
                      <p className={s.msgText}>{m.preview}</p>
                      <div className={s.tags}>
                        {m.tags.map((tag) => (
                          <Tag key={tag}>{tag}</Tag>
                        ))}
                      </div>
                    </>
                  );
                  const cls = `${s.msg} ${newIds.has(m.id) ? s.msgNew : ''}`;
                  return m.report_id ? (
                    <Link key={m.id} to={`/app/reports/${m.report_id}`} className={cls}>
                      {inner}
                    </Link>
                  ) : (
                    <div key={m.id} className={cls}>
                      {inner}
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* Ask your data */}
          <section>
            <h2>{t('dashboard.ask.title')}</h2>
            <AskBox />
          </section>
        </div>

        {/* Right: neighborhoods + urgent queue */}
        <div className={s.col}>
          <section>
            <h2>{t('dashboard.areas')}</h2>
            <div className={s.list}>
              {areas.data?.map((a) => (
                <AreaRow key={a.area} a={a} reportsLabel={t('dashboard.area.reports')} />
              ))}
            </div>
          </section>

          <section>
            <h2>{t('dashboard.urgentQueue')}</h2>
            {urgent.length === 0 ? (
              <p className="muted">{t('dashboard.urgentEmpty')}</p>
            ) : (
              <div className={s.list}>
                {urgent.map((r) => (
                  <Link key={r.id} to={`/app/reports/${r.id}`} className={s.urgentItem}>
                    <span className={s.urgentBody}>
                      <span className={s.urgentArea}>{r.area}</span>
                      <span className={s.urgentTags}>{(r.tags ?? []).slice(0, 2).join(' · ')}</span>
                    </span>
                    <UrgentPill />
                  </Link>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

function AreaRow({ a, reportsLabel }: { a: AreaCount; reportsLabel: string }) {
  const total = Math.max(1, a.reports);
  const powerPct = (a.without_power / total) * 100;
  const waterPct = (a.without_water / total) * 100;
  return (
    <div className={s.areaRow}>
      <div className={s.areaTop}>
        <span className={s.areaName}>{a.area}</span>
        <span className={`${s.areaCount} tnum`}>
          {a.reports} {reportsLabel}
        </span>
      </div>
      <div className={s.areaBarWrap} aria-hidden>
        <span className={`${s.areaBar} ${s.barPower}`} style={{ width: `${powerPct}%` }} />
        <span className={`${s.areaBar} ${s.barWater}`} style={{ width: `${waterPct}%` }} />
      </div>
      <div className={s.areaMeta}>
        <span className="tnum">{a.without_power} {labelPower(reportsLabel)}</span>
        <span className="tnum">{a.without_water} {labelWater(reportsLabel)}</span>
      </div>
    </div>
  );
}

// Compact inline labels derived from locale (keeps the row emoji-free).
function labelPower(reportsLabel: string) {
  return reportsLabel === 'reportes' ? 'sin luz' : 'no power';
}
function labelWater(reportsLabel: string) {
  return reportsLabel === 'reportes' ? 'sin agua' : 'no water';
}

function AskBox() {
  const t = useT();
  const ask = useAsk();
  const [q, setQ] = useState('');
  return (
    <>
      <form
        className={s.askForm}
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim()) ask.mutate(q.trim());
        }}
      >
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t('dashboard.ask.placeholder')}
          aria-label={t('dashboard.ask.title')}
        />
        <button type="submit" disabled={ask.isPending || !q.trim()}>
          {ask.isPending ? '…' : t('dashboard.ask.btn')}
        </button>
      </form>
      {ask.data && <div className={s.askAnswer}>{ask.data.answer}</div>}
    </>
  );
}
