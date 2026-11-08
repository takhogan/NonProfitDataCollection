import { useI18n } from '../../locales/i18n';
import { formatRelative } from '../../locales/format';
import { Pill } from '../../ui/kit';
import { useT, type ProductKey } from '../i18n';

// Quiet by default; confirmed gets the one accent tint, review a soft amber.
const STATUS_TONE: Record<string, 'neutral' | 'accent' | 'ok' | 'warn' | 'danger'> = {
  draft: 'neutral',
  confirmed: 'ok',
  review: 'warn',
  superseded: 'neutral',
  withdrawn: 'neutral',
};

export function StatusPill({ status }: { status: string }) {
  const t = useT();
  const key = `reports.status.${status}` as ProductKey;
  return <Pill tone={STATUS_TONE[status] ?? 'neutral'}>{t(key)}</Pill>;
}

export function UrgentPill() {
  const t = useT();
  return <Pill tone="danger">{t('reports.urgent')}</Pill>;
}

/** Relative time ("5 min ago") in the active locale. */
export function Ago({ at }: { at: string }) {
  const { locale } = useI18n();
  return (
    <time dateTime={at} title={at}>
      {formatRelative(at, locale)}
    </time>
  );
}

const CHANNEL_LABEL: Record<string, ProductKey> = {
  whatsapp: 'channel.whatsapp',
  sms: 'channel.sms',
  telegram: 'channel.telegram',
  email: 'channel.email',
};

export function useChannelLabel() {
  const t = useT();
  return (channel: string) => {
    const k = CHANNEL_LABEL[channel];
    return k ? t(k) : channel;
  };
}

// Human, localized labels for extracted-field tags. Never show snake_case.
const TAG_LABEL: Record<string, { es: string; en: string }> = {
  no_power: { es: 'Sin luz', en: 'No power' },
  no_water: { es: 'Sin agua', en: 'No water' },
  intermittent_power: { es: 'Luz intermitente', en: 'Intermittent power' },
  power_restored: { es: 'Luz restablecida', en: 'Power restored' },
  water_restored: { es: 'Agua restablecida', en: 'Water restored' },
  elderly: { es: 'Adulto mayor', en: 'Elderly' },
  medical: { es: 'Médico', en: 'Medical' },
  urgent: { es: 'Urgente', en: 'Urgent' },
};

// Human labels for service type + status (shown as "Luz · No disponible").
const SERVICE_LABEL: Record<string, { es: string; en: string }> = {
  electricity: { es: 'Luz', en: 'Power' },
  piped_water: { es: 'Agua', en: 'Water' },
};
const SERVICE_STATUS_LABEL: Record<string, { es: string; en: string }> = {
  unavailable: { es: 'No disponible', en: 'Unavailable' },
  available: { es: 'Disponible', en: 'Available' },
  intermittent: { es: 'Intermitente', en: 'Intermittent' },
  unknown: { es: 'Desconocido', en: 'Unknown' },
};

function humanize(raw: string): string {
  // Fallback: turn snake_case into Title Case rather than ever showing raw.
  return raw
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/** Hook returning localized label functions for tags / service / status. */
export function useLabels() {
  const { lang } = useI18n();
  return {
    tag: (raw: string) => TAG_LABEL[raw]?.[lang] ?? humanize(raw),
    service: (raw: string) => SERVICE_LABEL[raw]?.[lang] ?? humanize(raw),
    serviceStatus: (raw: string) => SERVICE_STATUS_LABEL[raw]?.[lang] ?? humanize(raw),
  };
}
