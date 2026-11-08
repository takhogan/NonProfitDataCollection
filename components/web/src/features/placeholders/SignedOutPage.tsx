import { Link } from 'react-router';
import { useI18n } from '../../locales/i18n';

export default function SignedOutPage() {
  const { t } = useI18n();
  return (
    <main style={{ padding: '2rem 1rem', maxWidth: 480, margin: '0 auto' }}>
      <h1>{t('signedOut.title')}</h1>
      <p>{t('signedOut.body')}</p>
      <Link to="/">{t('signedOut.again')}</Link>
    </main>
  );
}
