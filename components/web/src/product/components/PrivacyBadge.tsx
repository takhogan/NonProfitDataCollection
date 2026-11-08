import { ShieldCheck } from 'lucide-react';
import { useDataProtection } from '../../api/product/queries';
import { useI18n } from '../../locales/i18n';
import type { DataProtectionConfig } from '../../api/product';

const LABEL: Record<DataProtectionConfig['preset'], { es: string; en: string }> = {
  standard: { es: 'Estándar', en: 'Standard' },
  protected: { es: 'Protegido', en: 'Protected' },
  minimal: { es: 'Mínimo', en: 'Minimal' },
  custom: { es: 'Personalizado', en: 'Custom' },
};

/** Shows the org's active data-protection level (brief: a badge on the dashboard).
    Styled as quiet secondary text with a thin shield icon, not a loud pill. */
export function PrivacyBadge() {
  const { lang } = useI18n();
  const dp = useDataProtection();
  if (!dp.data) return null;
  const preset = dp.data.preset;
  const prefix = lang === 'es' ? 'Protección' : 'Protection';
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', color: 'var(--muted)', fontSize: '0.9rem' }}>
      <ShieldCheck size={15} strokeWidth={1.5} aria-hidden />
      {prefix}: {LABEL[preset][lang]}
    </span>
  );
}
