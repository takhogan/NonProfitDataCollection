import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router';
import { useReports } from '../../api/product/queries';
import { useT, type ProductKey } from '../i18n';
import { Tag } from '../../ui/kit';
import { Segmented } from '../../ui/Segmented';
import { Ago, StatusPill, UrgentPill, useChannelLabel } from '../components/bits';
import { PrivacyBadge } from '../components/PrivacyBadge';
import type { ReportStatus } from '../../api/product';
import s from './Reports.module.css';

const STATUSES: ReportStatus[] = ['draft', 'confirmed', 'review', 'superseded', 'withdrawn'];

export default function ReportsPage() {
  const t = useT();
  const channelLabel = useChannelLabel();
  const [status, setStatus] = useState<ReportStatus | 'all'>('all');
  const reports = useReports(status === 'all' ? undefined : status);

  const segments = [
    { value: 'all' as const, label: t('reports.all') },
    ...STATUSES.map((st) => ({ value: st, label: t(`reports.status.${st}` as ProductKey) })),
  ];

  return (
    <>
      <div className={s.pageHead}>
        <h1>{t('reports.title')}</h1>
        <PrivacyBadge />
      </div>

      <div className={s.filterBar}>
        <Segmented options={segments} value={status} onChange={setStatus} ariaLabel={t('reports.title')} />
      </div>

      {reports.isPending ? (
        <p className="muted">{t('common.loading')}</p>
      ) : !reports.data || reports.data.length === 0 ? (
        <p className="muted">{t('reports.empty')}</p>
      ) : (
        <div className={s.group}>
          {reports.data.map((r) => (
            <Link key={r.id} to={`/app/reports/${r.id}`} className={s.reportRow}>
              <div className={s.reportMain}>
                <div className={s.reportTitle}>
                  <span className={s.reportArea}>{r.area ?? '—'}</span>
                  {r.urgent && <UrgentPill />}
                  <StatusPill status={r.status} />
                </div>
                <div className={s.reportMeta}>
                  {r.service_type ? <span>{r.service_type} · {r.service_status}</span> : null}
                  <span>{r.reporter_name ?? t('reports.nameHidden')}</span>
                  {r.reporter_phone ? <span className="tnum">{r.reporter_phone}</span> : null}
                </div>
                <div className={s.cellTags}>
                  {(r.tags ?? []).slice(0, 3).map((tag) => (
                    <Tag key={tag}>{tag}</Tag>
                  ))}
                </div>
              </div>
              <div className={s.reportRight}>
                <span className={s.reportWhen}>
                  <Ago at={r.submitted_at} />
                  <span className={s.reportChan}>{channelLabel(r.source_channel)}</span>
                </span>
                <ChevronRight size={18} strokeWidth={1.75} className={s.chev} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
