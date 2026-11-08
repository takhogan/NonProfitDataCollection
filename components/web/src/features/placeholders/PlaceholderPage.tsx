import type { MessageKey } from '../../locales/es';
import { useI18n } from '../../locales/i18n';

export default function PlaceholderPage({ title, req }: { title: MessageKey; req?: string }) {
  const { t } = useI18n();
  return (
    <>
      <h1>{t(title)}</h1>
      {req && <p className="muted">{t('placeholder.notBuilt', { req })}</p>}
    </>
  );
}
