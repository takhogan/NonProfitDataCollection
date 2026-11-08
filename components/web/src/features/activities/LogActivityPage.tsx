import { useMemo, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { useNavigate, useSearchParams } from 'react-router';
import type {
  ActivityCreate,
  ActivityStatus,
  ActivityType,
  ActivityVisibility,
  AreaRef,
  NeedCategory,
  Weekday,
} from '../../api';
import { useAreas, useCreateActivity, useMeetingPoints } from '../../api/queries';
import { useI18n } from '../../locales/i18n';
import { commonStyles, Loading, QueryError, SaveError } from '../../ui/common';
import { CATEGORIES } from '../filters';
import { WEEKDAYS } from './schedule';
import { useOperationKey } from './useOperationKey';
import f from './form.module.css';

export const ACTIVITY_TYPES: ActivityType[] = ['water_distribution_point', 'water_delivery', 'charging_point', 'other'];
const VISIBILITIES: ActivityVisibility[] = ['all_providers', 'internal', 'public'];
const STATUSES: ActivityStatus[] = ['active', 'planned', 'paused'];

export interface ActivityFormValues {
  type: ActivityType;
  category: NeedCategory;
  area_ids: string[];
  schedule_kind: 'one_off' | 'recurring';
  date: string;
  days: Weekday[];
  start_time: string;
  end_time: string;
  capacity: string;
  public_location_id: string;
  visibility: ActivityVisibility;
  status: ActivityStatus;
}

function defaultTypeFor(c: NeedCategory): ActivityType {
  return c === 'charging' ? 'charging_point' : 'water_distribution_point';
}

export function toCommand(v: ActivityFormValues, operationKey: string): ActivityCreate {
  const capacity = v.capacity.trim() === '' ? null : Number(v.capacity);
  return {
    operation_key: operationKey,
    type: v.type,
    category: v.category,
    area_ids: v.area_ids,
    schedule:
      v.schedule_kind === 'one_off'
        ? { kind: 'one_off', date: v.date, start_time: v.start_time, end_time: v.end_time }
        : { kind: 'recurring', days: v.days, start_time: v.start_time, end_time: v.end_time },
    capacity:
      capacity === null ? null : { value: capacity, unit: v.category === 'charging' ? 'devices' : 'liters' },
    public_location_id: v.public_location_id || null,
    visibility: v.visibility,
    status: v.status,
  };
}

/** WEB-014 */
export default function LogActivityPage() {
  const { t } = useI18n();
  const [params] = useSearchParams();
  const areas = useAreas();
  if (areas.isPending) return <Loading />;
  if (areas.isError) return <QueryError error={areas.error} onRetry={() => areas.refetch()} />;
  const preArea = params.get('area');
  const preCat = params.get('category') as NeedCategory | null;
  const category = preCat && CATEGORIES.includes(preCat) ? preCat : 'water_drinking';
  const sectors = areas.data.filter((a) => a.level === 'sector');
  return (
    <>
      <h1>{t('log.title')}</h1>
      <ActivityForm
        sectors={sectors}
        parishes={areas.data.filter((a) => a.level === 'parish')}
        defaults={{
          type: defaultTypeFor(category),
          category,
          area_ids: preArea && sectors.some((s) => s.id === preArea) ? [preArea] : [],
          schedule_kind: 'recurring',
          date: '',
          days: [],
          start_time: '08:00',
          end_time: '12:00',
          capacity: '',
          public_location_id: '',
          visibility: 'all_providers',
          status: 'active',
        }}
      />
    </>
  );
}

function ActivityForm({
  sectors,
  parishes,
  defaults,
}: {
  sectors: AreaRef[];
  parishes: AreaRef[];
  defaults: ActivityFormValues;
}) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const create = useCreateActivity();
  const op = useOperationKey();
  const [areaFilter, setAreaFilter] = useState('');
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<ActivityFormValues>({ defaultValues: defaults });
  const [category, scheduleKind, areaIds] = useWatch({ control, name: ['category', 'schedule_kind', 'area_ids'] });
  const selected = useMemo(() => (Array.isArray(areaIds) ? areaIds : areaIds ? [areaIds] : []), [areaIds]);
  const meetingPoints = useMeetingPoints(selected);

  const submit = handleSubmit(async (values) => {
    const cmd = toCommand(values, '');
    const key = op.keyFor({ ...cmd, operation_key: undefined });
    try {
      const saved = await create.mutateAsync({ ...cmd, operation_key: key });
      op.reset();
      navigate('/activities', { state: { savedId: saved.id } });
    } catch {
      // Shown by <SaveError>; values stay in the form (WEB-005).
    }
  });

  const needle = areaFilter.trim().toLowerCase();
  const matches = (a: AreaRef) =>
    !needle || a.name.toLowerCase().includes(needle) || a.aliases.some((x) => x.toLowerCase().includes(needle));

  return (
    <form onSubmit={submit} noValidate className={f.form}>
      <div className={f.row}>
        <label className={f.field}>
          {t('log.category')}
          <select {...register('category')}>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {t(`category.${c}`)}
              </option>
            ))}
          </select>
        </label>
        <label className={f.field}>
          {t('log.type')}
          <select {...register('type')}>
            {ACTIVITY_TYPES.map((x) => (
              <option key={x} value={x}>
                {t(`activityType.${x}`)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <fieldset aria-describedby={errors.area_ids ? 'areas-error' : undefined}>
        <legend>{t('log.areas')}</legend>
        <label className={f.field}>
          {t('log.areaFilter')}
          <input type="text" value={areaFilter} onChange={(e) => setAreaFilter(e.target.value)} />
        </label>
        {parishes.map((p) => {
          const inParish = sectors.filter((s) => s.parent_id === p.id);
          return (
            <div key={p.id} className={f.group}>
              <div className={f.groupTitle}>{p.name}</div>
              {inParish.map((s) => (
                <label key={s.id} className={f.check} hidden={!matches(s) && !selected.includes(s.id)}>
                  <input
                    type="checkbox"
                    value={s.id}
                    {...register('area_ids', { validate: (v) => (v && v.length > 0) || 'log.errors.areas' })}
                  />
                  {s.name}
                  {s.aliases.length > 0 && <span className="muted"> ({s.aliases.join(', ')})</span>}
                </label>
              ))}
            </div>
          );
        })}
        {errors.area_ids && (
          <p id="areas-error" className={f.error} role="alert">
            {t('log.errors.areas')}
          </p>
        )}
      </fieldset>

      <fieldset>
        <legend>{t('log.schedule')}</legend>
        <div className={f.row}>
          <label className={f.check}>
            <input type="radio" value="recurring" {...register('schedule_kind')} />
            {t('log.recurring')}
          </label>
          <label className={f.check}>
            <input type="radio" value="one_off" {...register('schedule_kind')} />
            {t('log.oneOff')}
          </label>
        </div>
        {scheduleKind === 'one_off' ? (
          <label className={f.field}>
            {t('log.date')}
            <input
              type="date"
              {...register('date', { validate: (v, all) => all.schedule_kind !== 'one_off' || !!v || 'log.errors.date' })}
              aria-invalid={!!errors.date}
            />
            {errors.date && <span className={f.error}>{t('log.errors.date')}</span>}
          </label>
        ) : (
          <div role="group" aria-label={t('log.days')}>
            <div className={f.days}>
              {WEEKDAYS.map((d) => (
                <label key={d} className={f.check}>
                  <input
                    type="checkbox"
                    value={d}
                    {...register('days', {
                      validate: (v, all) => all.schedule_kind !== 'recurring' || (v && v.length > 0) || 'log.errors.days',
                    })}
                  />
                  {t(`weekday.${d}`)}
                </label>
              ))}
            </div>
            {errors.days && <p className={f.error}>{t('log.errors.days')}</p>}
          </div>
        )}
        <div className={f.row}>
          <label className={f.field}>
            {t('log.start')}
            <input type="time" {...register('start_time', { required: true })} />
          </label>
          <label className={f.field}>
            {t('log.end')}
            <input
              type="time"
              {...register('end_time', { validate: (v, all) => v > all.start_time || 'log.errors.endBeforeStart' })}
              aria-invalid={!!errors.end_time}
            />
            {errors.end_time && <span className={f.error}>{t('log.errors.endBeforeStart')}</span>}
          </label>
        </div>
        <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
          {t('log.timesCaracas')}
        </p>
      </fieldset>

      <div className={f.row}>
        <label className={f.field}>
          {t('log.capacity', { unit: t(`quantityUnit.${category === 'charging' ? 'devices' : 'liters'}`) })}
          <input
            type="number"
            inputMode="numeric"
            min={1}
            {...register('capacity', {
              validate: (v) => v.trim() === '' || (Number.isInteger(Number(v)) && Number(v) > 0) || 'log.errors.capacity',
            })}
            aria-invalid={!!errors.capacity}
          />
          <span className="muted" style={{ fontSize: '0.8rem' }}>
            {t('common.optional')}
          </span>
          {errors.capacity && <span className={f.error}>{t('log.errors.capacity')}</span>}
        </label>
        <label className={f.field}>
          {t('log.publicLocation')}
          <select {...register('public_location_id')}>
            <option value="">{t('log.noPublicLocation')}</option>
            {(meetingPoints.data ?? []).map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
          <span className="muted" style={{ fontSize: '0.8rem' }}>
            {selected.length === 0 ? t('log.pickAreasFirst') : t('log.publicLocationHint')}
          </span>
        </label>
      </div>

      <fieldset>
        <legend>{t('log.visibility')}</legend>
        {VISIBILITIES.map((v) => (
          <label key={v} className={f.check}>
            <input type="radio" value={v} {...register('visibility')} />
            <span>
              {t(`visibility.${v}`)}
              <span className="muted" style={{ display: 'block', fontSize: '0.85rem' }}>
                {t(`visibility.${v}.hint`)}
              </span>
            </span>
          </label>
        ))}
      </fieldset>

      <label className={f.field}>
        {t('log.status')}
        <select {...register('status')}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`activityStatus.${s}`)}
            </option>
          ))}
        </select>
      </label>

      {create.isError && <SaveError error={create.error} onRetry={() => submit()} />}

      <div className={commonStyles.actions}>
        <button type="submit" disabled={create.isPending}>
          {create.isPending ? t('save.saving') : t('log.submit')}
        </button>
      </div>
    </form>
  );
}
