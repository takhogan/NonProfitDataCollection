import type { ReactNode } from 'react';
import { ApiError, type CoverageStatus } from '../api';
import type { MessageKey } from '../locales/es';
import { useI18n } from '../locales/i18n';
import s from './common.module.css';

export { s as commonStyles };

export function Loading() {
  const { t } = useI18n();
  return (
    <p role="status" className="muted">
      {t('common.loading')}
    </p>
  );
}

export function errorMessageKey(err: unknown): MessageKey {
  if (err instanceof ApiError) {
    const k = `errors.${err.code}` as MessageKey;
    return k;
  }
  return 'errors.internal';
}

export function QueryError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div role="alert" className={s.error}>
      <p style={{ margin: 0 }}>{t(errorMessageKey(error))}</p>
      {error instanceof ApiError && error.envelope.request_id && (
        <p className="muted" style={{ margin: '0.25rem 0 0', fontSize: '0.85rem' }}>
          {t('errors.requestId', { id: error.envelope.request_id })}
        </p>
      )}
      {onRetry && (
        <button type="button" className="secondary" onClick={onRetry} style={{ marginTop: '0.5rem' }}>
          {t('common.retry')}
        </button>
      )}
    </div>
  );
}

/** WEB-005: a failed save is shown, input is kept, retry reuses the operation key. */
export function SaveError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <div role="alert" className={s.error}>
      <p style={{ margin: 0, fontWeight: 600 }}>{t('save.failed')}</p>
      <p style={{ margin: '0.25rem 0' }}>{t(errorMessageKey(error))}</p>
      <p className="muted" style={{ margin: '0 0 0.5rem', fontSize: '0.85rem' }}>
        {t('save.kept')}
      </p>
      <button type="button" onClick={onRetry}>
        {t('save.retry')}
      </button>
    </div>
  );
}

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'success' }) {
  return (
    <div className={tone === 'success' ? s.success : s.notice} role={tone === 'success' ? 'status' : undefined}>
      {children}
    </div>
  );
}

export function CoverageStatusBadge({ status, highNeed }: { status: CoverageStatus; highNeed?: boolean }) {
  const { t } = useI18n();
  return (
    <span className={`${s.status} ${s[status]}`}>
      {t(`coverage.status.${status}`)}
      {highNeed && status === 'uncovered' ? ` · ${t('coverage.highNeed')}` : ''}
    </span>
  );
}
