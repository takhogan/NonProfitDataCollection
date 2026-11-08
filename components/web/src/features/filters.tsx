import { useSearchParams } from 'react-router';
import type { AreaLevel, Bucket, NeedCategory } from '../api';
import { useI18n } from '../locales/i18n';

export const BUCKETS: Bucket[] = ['6h', '24h', '7d'];
export const CATEGORIES: NeedCategory[] = ['water_drinking', 'water_other', 'charging'];

const isBucket = (v: string | null): v is Bucket => !!v && (BUCKETS as string[]).includes(v);
const isCategory = (v: string | null): v is NeedCategory => !!v && (CATEGORIES as string[]).includes(v);

/** Filters live in the URL (shareable, not personal data, nothing persisted). */
export function useAggregateFilters() {
  const [params, setParams] = useSearchParams();
  const bucket: Bucket = isBucket(params.get('bucket')) ? (params.get('bucket') as Bucket) : '24h';
  const category = isCategory(params.get('category')) ? (params.get('category') as NeedCategory) : undefined;
  const level: AreaLevel = params.get('level') === 'parish' ? 'parish' : 'sector';
  const set = (key: string, value: string | undefined) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };
  return { bucket, category, level, set, params };
}

export function BucketSelect({ value, onChange }: { value: Bucket; onChange(b: Bucket): void }) {
  const { t } = useI18n();
  return (
    <label>
      {t('filters.bucket')}
      <select value={value} onChange={(e) => onChange(e.target.value as Bucket)}>
        {BUCKETS.map((b) => (
          <option key={b} value={b}>
            {t(`bucket.${b}`)}
          </option>
        ))}
      </select>
    </label>
  );
}

export function CategorySelect({
  value,
  onChange,
  allowAll = true,
}: {
  value: NeedCategory | undefined;
  onChange(c: NeedCategory | undefined): void;
  allowAll?: boolean;
}) {
  const { t } = useI18n();
  return (
    <label>
      {t('filters.category')}
      <select value={value ?? ''} onChange={(e) => onChange((e.target.value || undefined) as NeedCategory | undefined)}>
        {allowAll && <option value="">{t('filters.allCategories')}</option>}
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {t(`category.${c}`)}
          </option>
        ))}
      </select>
    </label>
  );
}

export function LevelSelect({ value, onChange }: { value: AreaLevel; onChange(l: AreaLevel): void }) {
  const { t } = useI18n();
  return (
    <label>
      {t('filters.level')}
      <select value={value} onChange={(e) => onChange(e.target.value as AreaLevel)}>
        <option value="sector">{t('level.sector')}</option>
        <option value="parish">{t('level.parish')}</option>
      </select>
    </label>
  );
}
