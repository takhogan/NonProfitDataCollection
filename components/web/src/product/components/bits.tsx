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
