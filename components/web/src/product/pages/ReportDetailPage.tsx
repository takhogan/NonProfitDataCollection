import { useEffect, useState } from 'react';
import { ChevronLeft } from 'lucide-react';
import { Link, useParams } from 'react-router';
import { useI18n } from '../../locales/i18n';
import { formatDateTime } from '../../locales/format';
import { useMe, usePatchReport, useReport } from '../../api/product/queries';
import { useT, type ProductKey } from '../i18n';
import { Tag } from '../../ui/kit';
import { Segmented } from '../../ui/Segmented';
import { StatusPill, UrgentPill, useChannelLabel } from '../components/bits';
import type { ReportStatus } from '../../api/product';
import s from './Reports.module.css';

const STATUSES: ReportStatus[] = ['draft', 'confirmed', 'review', 'superseded', 'withdrawn'];

export default function ReportDetailPage() {
  const t = useT();
  const { locale } = useI18n();
  const { reportId = '' } = useParams();
  const report = useReport(reportId);
  const patch = usePatchReport();
  const me = useMe();
  const channelLabel = useChannelLabel();

  const [notes, setNotes] = useState('');
  const [assignee, setAssignee] = useState<string>('');
  useEffect(() => {
    if (report.data) {
      setNotes(report.data.notes ?? '');
      setAssignee(report.data.assignee ?? '');
    }
  }, [report.data]);

  if (report.isPending) return <p className="muted">{t('common.loading')}</p>;
  if (report.isError || !report.data) return <p className="muted">{t('error.generic')}</p>;
  const r = report.data;

  const members = me.data?.memberships ?? [];
  const saveMeta = () => patch.mutate({ id: r.id, body: { notes, assignee: assignee || null } });

  return (
    <>
      <Link to="/app/reports" className={s.backLink}>
        <ChevronLeft size={18} strokeWidth={1.75} /> {t('reports.title')}
      </Link>
      <div className={s.detailTop}>
        <h1>{r.area ?? '—'}</h1>
        <div className={s.detailTopPills}>
          {r.urgent && <UrgentPill />}
          <StatusPill status={r.status} />
        </div>
      </div>

      <div className={s.detailGrid}>
        {/* Transcript + extracted fields */}
        <div>
          <section className={s.section}>
            <h2>{t('reports.transcript')}</h2>
            <div className={s.transcript}>
              {(r.transcript ?? []).map((line, i) => (
                <div key={i} className={`${s.tLine} ${line.from === 'bot' ? s.tBot : s.tReporter}`}>
                  <span className={s.tWho}>{line.from === 'bot' ? t('reports.from.bot') : t('reports.from.reporter')}</span>
                  {line.text}
                </div>
              ))}
            </div>
          </section>

          <section className={s.section}>
            <h2>{t('reports.extracted')}</h2>
            <div className={s.detailTags}>
              {(r.tags ?? []).map((tag) => (
                <Tag key={tag}>{tag}</Tag>
              ))}
            </div>
            <dl className={s.fields}>
              {Object.entries(r.extracted_fields ?? {}).map(([k, v]) => (
                <div key={k} className={s.fieldRow}>
                  <dt className={s.fieldKey}>{k}</dt>
                  <dd className={s.fieldVal}>{formatValue(v)}</dd>
                </div>
              ))}
            </dl>
          </section>
        </div>

        {/* Meta + triage */}
        <div>
          <div className={s.metaList}>
            <div className={s.metaRow}>
              <span>{t('reports.col.when')}</span>
              <span className="tnum">{formatDateTime(r.submitted_at, locale)}</span>
            </div>
            <div className={s.metaRow}>
              <span>{t('reports.col.service')}</span>
              <span>{r.service_type ? `${r.service_type} · ${r.service_status}` : '—'}</span>
            </div>
            <div className={s.metaRow}>
              <span>{t('reports.col.reporter')}</span>
              <span>{r.reporter_name ?? t('reports.nameHidden')}</span>
            </div>
            {r.reporter_phone && (
              <div className={s.metaRow}>
                <span>Tel</span>
                <span className="tnum">{r.reporter_phone}</span>
              </div>
            )}
            <div className={s.metaRow}>
              <span>{t('reports.col.area')}</span>
              <span>{r.area ?? '—'} · {channelLabel(r.source_channel)}</span>
            </div>
          </div>

          <span className={s.triageLabel}>{t('reports.col.status')}</span>
          <div className={s.statusSeg}>
            <Segmented
              options={STATUSES.map((st) => ({ value: st, label: t(`reports.status.${st}` as ProductKey) }))}
              value={r.status as ReportStatus}
              onChange={(st) => patch.mutate({ id: r.id, body: { status: st } })}
              ariaLabel={t('reports.col.status')}
            />
          </div>

          <span className={s.triageLabel}>{t('reports.assignee')}</span>
          {/* No /org/members endpoint yet (BACKEND_ENDPOINTS_NEEDED #1); current user only. */}
          <select id="assignee" value={assignee} onChange={(e) => setAssignee(e.target.value)} style={{ width: '100%', marginBottom: '1.1rem' }}>
            <option value="">{t('reports.unassigned')}</option>
            {me.data && members.length > 0 && (
              <option value={me.data.id}>{me.data.display_name || me.data.email}</option>
            )}
          </select>

          <span className={s.triageLabel}>{t('reports.notes')}</span>
          <textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} style={{ width: '100%' }} />
          <div className={s.saveRow}>
            <button type="button" disabled={patch.isPending} onClick={saveMeta}>
              {patch.isPending ? t('common.saving') : t('common.save')}
            </button>
            {patch.isSuccess && !patch.isPending && <span className="muted" style={{ fontSize: '0.85rem' }}>{t('common.saved')}</span>}
          </div>
        </div>
      </div>
    </>
  );
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (Array.isArray(v)) return v.length ? v.join(', ') : '—';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  return String(v);
}
