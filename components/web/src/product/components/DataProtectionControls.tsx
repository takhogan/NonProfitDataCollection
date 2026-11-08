import { Check } from 'lucide-react';
import { useI18n } from '../../locales/i18n';
import { useT, type ProductKey } from '../i18n';
import type { DataProtectionConfig } from '../../api/product';
import s from '../pages/Onboarding.module.css';

type Preset = DataProtectionConfig['preset'];

const PRESETS: Exclude<Preset, 'custom'>[] = ['standard', 'protected', 'minimal'];

/** Default field values per preset (mirrors the contract's semantics). */
export function presetDefaults(preset: Preset): Partial<DataProtectionConfig> {
  switch (preset) {
    case 'protected':
      return { store_names: false, location_precision: 'area', raw_message_retention_days: 7, mask_phone_numbers: true, redact_exports: true, individual_records_roles: ['org_admin', 'coordinator'] };
    case 'minimal':
      return { store_names: false, location_precision: 'area', raw_message_retention_days: 1, mask_phone_numbers: true, redact_exports: true, individual_records_roles: ['org_admin'] };
    case 'standard':
      return { store_names: true, location_precision: 'precise', raw_message_retention_days: 90, mask_phone_numbers: false, redact_exports: false, individual_records_roles: ['org_admin', 'coordinator'] };
    default:
      return {};
  }
}

/**
 * The data-protection control set, shared by the onboarding step and Settings.
 * Choosing a preset fills the detailed fields; editing any detail switches the
 * preset to `custom` (the caller decides, via `onChange`).
 */
export function DataProtectionControls({
  value,
  onChange,
}: {
  value: DataProtectionConfig;
  onChange: (next: DataProtectionConfig) => void;
}) {
  const t = useT();
  const { lang } = useI18n();

  const choosePreset = (preset: Exclude<Preset, 'custom'>) => {
    onChange({ ...value, preset, ...presetDefaults(preset) } as DataProtectionConfig);
  };
  const setField = <K extends keyof DataProtectionConfig>(k: K, v: DataProtectionConfig[K]) => {
    onChange({ ...value, [k]: v, preset: 'custom' });
  };

  return (
    <div>
      <p className={s.sub} style={{ marginBottom: '1rem' }}>{t('dp.intro')}</p>

      <div className={s.optionGroup} style={{ marginBottom: '1.5rem' }}>
        {PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            className={`${s.option} ${value.preset === p ? s.optionOn : ''}`}
            onClick={() => choosePreset(p)}
            aria-pressed={value.preset === p}
          >
            <div className={s.optionBody}>
              <h3>
                {t(`dp.preset.${p}` as ProductKey)}
                {p === 'protected' && <span className={s.recTag}>{t('dp.recommended')}</span>}
              </h3>
              <p>{t(`dp.preset.${p}Desc` as ProductKey)}</p>
            </div>
            {value.preset === p && <Check size={19} strokeWidth={2} className={s.optionCheck} />}
          </button>
        ))}
      </div>

      <h3 style={{ marginTop: 0 }}>{t('dp.preset.custom')}</h3>

      <div className={s.row2}>
        <label className={s.field} style={{ flexDirection: 'row', alignItems: 'center', gap: '0.5rem' }}>
          <input type="checkbox" checked={value.store_names} onChange={(e) => setField('store_names', e.target.checked)} />
          {t('dp.storeNames')}
        </label>
        <label className={s.field} style={{ flexDirection: 'row', alignItems: 'center', gap: '0.5rem' }}>
          <input type="checkbox" checked={value.mask_phone_numbers} onChange={(e) => setField('mask_phone_numbers', e.target.checked)} />
          {t('dp.mask')}
        </label>
      </div>

      <div className={s.row2}>
        <div className={s.field}>
          <label htmlFor="dp-loc">{t('dp.location')}</label>
          <select id="dp-loc" value={value.location_precision} onChange={(e) => setField('location_precision', e.target.value as DataProtectionConfig['location_precision'])}>
            <option value="area">{t('dp.location.area')}</option>
            <option value="precise">{t('dp.location.precise')}</option>
          </select>
        </div>
        <div className={s.field}>
          <label htmlFor="dp-ret">{t('dp.retention')}</label>
          <input id="dp-ret" type="number" min={1} value={value.raw_message_retention_days ?? 90} onChange={(e) => setField('raw_message_retention_days', Number(e.target.value))} />
        </div>
      </div>

      <div className={s.row2}>
        <label className={s.field} style={{ flexDirection: 'row', alignItems: 'center', gap: '0.5rem' }}>
          <input type="checkbox" checked={value.redact_exports} onChange={(e) => setField('redact_exports', e.target.checked)} />
          {t('dp.redact')}
        </label>
        <label className={s.field} style={{ flexDirection: 'row', alignItems: 'center', gap: '0.5rem' }}>
          <input type="checkbox" checked={value.audit_log_enabled ?? true} onChange={(e) => setField('audit_log_enabled', e.target.checked)} />
          {t('dp.audit')}
        </label>
      </div>

      <p className="muted" style={{ fontSize: '0.82rem', marginTop: '0.75rem', lineHeight: 1.45 }} lang={lang}>
        {t('dp.enforceNote')}
      </p>
    </div>
  );
}
