import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { useI18n } from '../../locales/i18n';
import { useT } from '../i18n';
import s from './Auth.module.css';

/** Shared chrome for the login / signup cards: sky background + brand bar. */
export function AuthFrame({ children }: { children: ReactNode }) {
  const t = useT();
  const { lang, setLang } = useI18n();
  return (
    <div className={s.page}>
      <div className={s.bar}>
        <Link to="/" className={s.brand}>
          {t('brand.name')}
        </Link>
        <button type="button" className="secondary" onClick={() => setLang(lang === 'es' ? 'en' : 'es')}>
          {lang === 'es' ? 'EN' : 'ES'}
        </button>
      </div>
      <div className={s.center}>
        <div className={s.card}>{children}</div>
      </div>
    </div>
  );
}
