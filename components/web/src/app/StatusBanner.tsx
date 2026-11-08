import { useStatus } from '../api/queries';
import { useI18n } from '../locales/i18n';
import s from './Layout.module.css';

/** NFR-07: lag above 2 minutes is user-visible. */
export const LAG_THRESHOLD_SECONDS = 120;

/** WEB-007: intake lag, stale indicators, degraded services. */
export function StatusBanner() {
  const { t } = useI18n();
  const { data } = useStatus();
  if (!data) return null;
  const messages: string[] = [];
  if (data.intake_lag_seconds > LAG_THRESHOLD_SECONDS) {
    messages.push(t('status.lag', { minutes: Math.round(data.intake_lag_seconds / 60) }));
  }
  if (data.stale_indicator_count > 0) {
    messages.push(t('status.stale', { count: data.stale_indicator_count }));
  }
  if (data.degraded_services.length > 0) {
    messages.push(t('status.degraded', { services: data.degraded_services.join(', ') }));
  }
  return (
    <div role="status" aria-live="polite">
      {messages.length > 0 && (
        <div className={s.banner}>
          <strong>{t('status.title')}</strong>
          <ul>
            {messages.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
