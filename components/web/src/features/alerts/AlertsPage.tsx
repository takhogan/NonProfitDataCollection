import { useState } from 'react';
import { Link } from 'react-router';
import type { AlertTrigger, AreaRef, NeedCategory } from '../../api';
import {
  useAlerts,
  useAlertSubscriptions,
  useAreas,
  useCreateAlertSubscription,
  useDeleteAlertSubscription,
  useMuteAlertSubscription,
} from '../../api/queries';
import { formatDateTime } from '../../locales/format';
import { useI18n } from '../../locales/i18n';
import { commonStyles, Loading, QueryError, SaveError } from '../../ui/common';
import { Count, Insufficient } from '../../ui/honest';
import { useOperationKey } from '../activities/useOperationKey';
import { CATEGORIES } from '../filters';
import f from '../activities/form.module.css';
import s from '../activities/activities.module.css';

type TriggerKind = AlertTrigger['kind'];
const TRIGGERS: TriggerKind[] = ['new_urgent', 'active_needs_above', 'became_uncovered', 'external_outage'];

/** WEB-016 */
export default function AlertsPage() {
  const { t, locale } = useI18n();
  const subs = useAlertSubscriptions();
  const alerts = useAlerts();
  const areas = useAreas();
  const areaName = (id: string) => areas.data?.find((a) => a.id === id)?.name ?? id;

  return (
    <>
      <h1>{t('alerts.title')}</h1>
      <p className="muted">{t('alerts.deliveryNote')}</p>

      <h2>{t('alerts.recent')}</h2>
      {alerts.isPending ? (
        <Loading />
      ) : alerts.isError ? (
        <QueryError error={alerts.error} onRetry={() => alerts.refetch()} />
      ) : alerts.data.length === 0 ? (
        <p>{t('alerts.noneRecent')}</p>
      ) : (
        <ul>
          {alerts.data.map((a) => (
            <li key={a.id} style={{ marginBottom: '0.4rem' }}>
              <time dateTime={a.created_at}>{formatDateTime(a.created_at, locale)}</time> —{' '}
              <Link to={`/areas/${a.area.id}`}>{a.area.name}</Link>, {t(`category.${a.category}`)}:{' '}
              {t(`trigger.${a.trigger_kind}`)} ·{' '}
              {a.active_needs === null ? <Insufficient /> : <Count value={a.active_needs} unit="needs" />}
            </li>
          ))}
        </ul>
      )}

      <h2>{t('alerts.subscriptions')}</h2>
      {subs.isPending ? (
        <Loading />
      ) : subs.isError ? (
        <QueryError error={subs.error} onRetry={() => subs.refetch()} />
      ) : subs.data.length === 0 ? (
        <p>{t('alerts.noSubscriptions')}</p>
      ) : (
        <ul className={s.list}>
          {subs.data.map((sub) => (
            <SubscriptionItem
              key={sub.id}
              id={sub.id}
              muted={sub.muted}
              summary={`${sub.area_ids.map(areaName).join(', ')} · ${t(`category.${sub.category}`)} · ${triggerText(sub.trigger, t)}`}
            />
          ))}
        </ul>
      )}

      <h2>{t('alerts.new')}</h2>
      {areas.data && <NewSubscriptionForm areas={areas.data} />}
    </>
  );
}

function triggerText(tr: AlertTrigger, t: ReturnType<typeof useI18n>['t']) {
  return tr.kind === 'active_needs_above' ? t('trigger.active_needs_above_n', { n: tr.threshold }) : t(`trigger.${tr.kind}`);
}

function SubscriptionItem({ id, muted, summary }: { id: string; muted: boolean; summary: string }) {
  const { t } = useI18n();
  const mute = useMuteAlertSubscription();
  const del = useDeleteAlertSubscription();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const busy = mute.isPending || del.isPending;
  return (
    <li className={s.card}>
      <p style={{ margin: '0 0 0.5rem' }}>
        {summary} {muted && <span className={s.status}>{t('alerts.muted')}</span>}
      </p>
      {(mute.error || del.error) && (
        <SaveError
          error={mute.error ?? del.error}
          onRetry={() => (mute.error ? mute.mutate({ id, muted: !muted }) : del.mutate(id))}
        />
      )}
      <div className={commonStyles.actions}>
        <button type="button" className="secondary" disabled={busy} onClick={() => mute.mutate({ id, muted: !muted })}>
          {muted ? t('alerts.unmute') : t('alerts.mute')}
        </button>
        {confirmDelete ? (
          <>
            <button type="button" className="danger" disabled={busy} onClick={() => del.mutate(id)}>
              {t('alerts.deleteConfirm')}
            </button>
            <button type="button" className="secondary" onClick={() => setConfirmDelete(false)}>
              {t('common.cancel')}
            </button>
          </>
        ) : (
          <button type="button" className="danger" disabled={busy} onClick={() => setConfirmDelete(true)}>
            {t('alerts.delete')}
          </button>
        )}
      </div>
    </li>
  );
}

function NewSubscriptionForm({ areas }: { areas: AreaRef[] }) {
  const { t } = useI18n();
  const create = useCreateAlertSubscription();
  const op = useOperationKey();
  const [areaIds, setAreaIds] = useState<string[]>([]);
  const [category, setCategory] = useState<NeedCategory>('water_drinking');
  const [kind, setKind] = useState<TriggerKind>('new_urgent');
  const [threshold, setThreshold] = useState('20');
  const [touched, setTouched] = useState(false);
  const [saved, setSaved] = useState(false);
  const thresholdOk = kind !== 'active_needs_above' || (Number.isInteger(Number(threshold)) && Number(threshold) > 0);
  const valid = areaIds.length > 0 && thresholdOk;

  const submit = async () => {
    setTouched(true);
    setSaved(false);
    if (!valid) return;
    const trigger: AlertTrigger =
      kind === 'active_needs_above' ? { kind, threshold: Number(threshold) } : ({ kind } as AlertTrigger);
    const body = { area_ids: areaIds, category, trigger };
    try {
      await create.mutateAsync({ ...body, operation_key: op.keyFor(body) });
      op.reset();
      setAreaIds([]);
      setTouched(false);
      setSaved(true);
    } catch {
      /* SaveError below */
    }
  };

  return (
    <form
      className={f.form}
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <fieldset>
        <legend>{t('alerts.areas')}</legend>
        {areas
          .filter((a) => a.level === 'parish')
          .map((p) => (
            <div key={p.id} className={f.group}>
              <label className={f.check}>
                <input
                  type="checkbox"
                  checked={areaIds.includes(p.id)}
                  onChange={(e) => setAreaIds((ids) => (e.target.checked ? [...ids, p.id] : ids.filter((x) => x !== p.id)))}
                />
                <strong>{t('alerts.wholeParish', { name: p.name })}</strong>
              </label>
              {areas
                .filter((s) => s.parent_id === p.id)
                .map((sct) => (
                  <label key={sct.id} className={f.check} style={{ marginLeft: '1.5rem' }}>
                    <input
                      type="checkbox"
                      checked={areaIds.includes(sct.id)}
                      onChange={(e) =>
                        setAreaIds((ids) => (e.target.checked ? [...ids, sct.id] : ids.filter((x) => x !== sct.id)))
                      }
                    />
                    {sct.name}
                  </label>
                ))}
            </div>
          ))}
        {touched && areaIds.length === 0 && (
          <p className={f.error} role="alert">
            {t('log.errors.areas')}
          </p>
        )}
      </fieldset>
      <div className={f.row}>
        <label className={f.field}>
          {t('log.category')}
          <select value={category} onChange={(e) => setCategory(e.target.value as NeedCategory)}>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {t(`category.${c}`)}
              </option>
            ))}
          </select>
        </label>
        <label className={f.field}>
          {t('alerts.trigger')}
          <select value={kind} onChange={(e) => setKind(e.target.value as TriggerKind)}>
            {TRIGGERS.map((k) => (
              <option key={k} value={k}>
                {t(`trigger.${k}`)}
              </option>
            ))}
          </select>
        </label>
        {kind === 'active_needs_above' && (
          <label className={f.field}>
            {t('alerts.threshold')}
            <input type="number" min={1} value={threshold} onChange={(e) => setThreshold(e.target.value)} aria-invalid={!thresholdOk} />
            {!thresholdOk && <span className={f.error}>{t('log.errors.capacity')}</span>}
          </label>
        )}
      </div>
      {create.isError && <SaveError error={create.error} onRetry={() => void submit()} />}
      {saved && (
        <p role="status" className={commonStyles.success}>
          {t('alerts.created')}
        </p>
      )}
      <button type="submit" disabled={create.isPending}>
        {create.isPending ? t('save.saving') : t('alerts.create')}
      </button>
    </form>
  );
}
