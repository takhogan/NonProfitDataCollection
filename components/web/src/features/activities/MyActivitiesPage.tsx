import { useState } from 'react';
import { Link, useLocation } from 'react-router';
import type { Activity, ActivityUpdate, ActivityVisibility } from '../../api';
import { useActivities, useConfirmActivity, useUpdateActivity } from '../../api/queries';
import { useI18n } from '../../locales/i18n';
import { commonStyles, Loading, Notice, QueryError, SaveError } from '../../ui/common';
import { Freshness } from '../../ui/honest';
import { ExportButton } from '../exports/ExportButton';
import { activitiesCsv } from '../exports/csv';
import { formatQuantity, formatSchedule } from './schedule';
import { useOperationKey } from './useOperationKey';
import s from './activities.module.css';

/** WEB-015 */
export default function MyActivitiesPage() {
  const { t, lang } = useI18n();
  const location = useLocation();
  const savedId = (location.state as { savedId?: string } | null)?.savedId;
  const q = useActivities({ mine: true });

  return (
    <>
      <div className={commonStyles.headerRow}>
        <h1>{t('mine.title')}</h1>
        <div className={commonStyles.actions}>
          {q.data && q.data.length > 0 && (
            <ExportButton filename="mis-actividades" build={() => activitiesCsv(q.data, lang)} />
          )}
          <Link to="/activities/new">{t('nav.logActivity')}</Link>
        </div>
      </div>
      {savedId && <Notice tone="success">{t('mine.saved')}</Notice>}
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <QueryError error={q.error} onRetry={() => q.refetch()} />
      ) : q.data.length === 0 ? (
        <p>{t('mine.empty')}</p>
      ) : (
        <ul className={s.list}>
          {sortActivities(q.data).map((a) => (
            <ActivityCard key={a.id} activity={a} />
          ))}
        </ul>
      )}
    </>
  );
}

function sortActivities(items: Activity[]) {
  const rank = (a: Activity) => (a.unconfirmed ? 0 : a.status === 'ended' ? 3 : a.status === 'active' ? 1 : 2);
  return [...items].sort((a, b) => rank(a) - rank(b));
}

type Pending = { kind: 'confirm' } | { kind: 'update'; patch: Omit<ActivityUpdate, 'operation_key' | 'version'> };

function ActivityCard({ activity: a }: { activity: Activity }) {
  const { t, lang } = useI18n();
  const update = useUpdateActivity();
  const confirm = useConfirmActivity();
  const op = useOperationKey();
  const [last, setLast] = useState<Pending | null>(null);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [editing, setEditing] = useState(false);
  const busy = update.isPending || confirm.isPending;
  const error = update.error ?? confirm.error;

  const run = async (p: Pending) => {
    setLast(p);
    update.reset();
    confirm.reset();
    try {
      if (p.kind === 'confirm') {
        await confirm.mutateAsync({ id: a.id, operationKey: op.keyFor({ confirm: a.id, v: a.version }) });
      } else {
        const body = { ...p.patch, version: a.version };
        await update.mutateAsync({ id: a.id, cmd: { ...body, operation_key: op.keyFor({ id: a.id, ...body }) } });
      }
      op.reset();
      setLast(null);
      setConfirmEnd(false);
      setEditing(false);
    } catch {
      /* shown below with a retry */
    }
  };

  return (
    <li className={`${s.card} ${a.unconfirmed ? s.unconfirmed : ''}`}>
      <div className={s.cardHead}>
        <strong>{t(`activityType.${a.type}`)}</strong>
        <span className={s.status}>{t(`activityStatus.${a.status}`)}</span>
      </div>
      {a.unconfirmed && (
        <p className={s.warn} role="note">
          {t('mine.unconfirmed')}
        </p>
      )}
      <dl className={s.dl}>
        <dt>{t('filters.category')}</dt>
        <dd>{t(`category.${a.category}`)}</dd>
        <dt>{t('log.areas')}</dt>
        <dd>{a.areas.map((x) => x.name).join(', ')}</dd>
        {a.schedule && (
          <>
            <dt>{t('log.schedule')}</dt>
            <dd>{formatSchedule(a.schedule, lang)}</dd>
          </>
        )}
        <dt>{t('mine.capacity')}</dt>
        <dd>{a.capacity ? formatQuantity(a.capacity, lang) : <span className="muted">{t('mine.notGiven')}</span>}</dd>
        {a.public_location && (
          <>
            <dt>{t('log.publicLocation')}</dt>
            <dd>{a.public_location.name}</dd>
          </>
        )}
        <dt>{t('log.visibility')}</dt>
        <dd>{t(`visibility.${a.visibility}`)}</dd>
        <dt>{t('mine.lastConfirmed')}</dt>
        <dd>
          <Freshness iso={a.last_confirmed_at} />
        </dd>
      </dl>

      {editing && <EditPanel activity={a} busy={busy} onSave={(patch) => run({ kind: 'update', patch })} onCancel={() => setEditing(false)} />}

      {error && last && <SaveError error={error} onRetry={() => run(last)} />}

      {a.status !== 'ended' && !editing && (
        <div className={commonStyles.actions}>
          {a.status === 'active' && (
            <button type="button" disabled={busy} onClick={() => run({ kind: 'confirm' })}>
              {t('mine.stillActive')}
            </button>
          )}
          {a.status === 'active' ? (
            <button type="button" className="secondary" disabled={busy} onClick={() => run({ kind: 'update', patch: { status: 'paused' } })}>
              {t('mine.pause')}
            </button>
          ) : (
            <button type="button" className="secondary" disabled={busy} onClick={() => run({ kind: 'update', patch: { status: 'active' } })}>
              {a.status === 'planned' ? t('mine.start') : t('mine.resume')}
            </button>
          )}
          <button type="button" className="secondary" disabled={busy} onClick={() => setEditing(true)}>
            {t('mine.edit')}
          </button>
          {confirmEnd ? (
            <>
              <button type="button" className="danger" disabled={busy} onClick={() => run({ kind: 'update', patch: { status: 'ended' } })}>
                {t('mine.endConfirm')}
              </button>
              <button type="button" className="secondary" onClick={() => setConfirmEnd(false)}>
                {t('common.cancel')}
              </button>
            </>
          ) : (
            <button type="button" className="danger" disabled={busy} onClick={() => setConfirmEnd(true)}>
              {t('mine.end')}
            </button>
          )}
          {busy && <span role="status">{t('save.saving')}</span>}
        </div>
      )}
    </li>
  );
}

function EditPanel({
  activity: a,
  busy,
  onSave,
  onCancel,
}: {
  activity: Activity;
  busy: boolean;
  onSave(patch: { capacity: Activity['capacity']; visibility: ActivityVisibility }): void;
  onCancel(): void;
}) {
  const { t } = useI18n();
  const unit = a.category === 'charging' ? 'devices' : 'liters';
  const [capacity, setCapacity] = useState(a.capacity ? String(a.capacity.value) : '');
  const [visibility, setVisibility] = useState<ActivityVisibility>(a.visibility);
  const valid = capacity.trim() === '' || (Number.isInteger(Number(capacity)) && Number(capacity) > 0);
  return (
    <form
      className={s.edit}
      onSubmit={(e) => {
        e.preventDefault();
        if (!valid) return;
        onSave({ capacity: capacity.trim() === '' ? null : { value: Number(capacity), unit }, visibility });
      }}
    >
      <label>
        {t('log.capacity', { unit: t(`quantityUnit.${unit}`) })}
        <input type="number" min={1} value={capacity} onChange={(e) => setCapacity(e.target.value)} aria-invalid={!valid} />
      </label>
      <label>
        {t('log.visibility')}
        <select value={visibility} onChange={(e) => setVisibility(e.target.value as ActivityVisibility)}>
          {(['all_providers', 'internal', 'public'] as const).map((v) => (
            <option key={v} value={v}>
              {t(`visibility.${v}`)}
            </option>
          ))}
        </select>
      </label>
      <div className={commonStyles.actions}>
        <button type="submit" disabled={busy || !valid}>
          {busy ? t('save.saving') : t('common.save')}
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </button>
      </div>
    </form>
  );
}
