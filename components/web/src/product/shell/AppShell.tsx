import { Suspense } from 'react';
import { NavLink, Outlet } from 'react-router';
import { API_MODE } from '../../api/product';
import { useMe } from '../../api/product/queries';
import { useI18n } from '../../locales/i18n';
import { useT } from '../i18n';
import { useSignOut } from './session';
import s from './AppShell.module.css';

const NAV = [
  { to: '/app', label: 'nav.dashboard' as const, end: true },
  { to: '/app/reports', label: 'nav.reports' as const, end: false },
  { to: '/app/campaigns', label: 'nav.campaigns' as const, end: false },
  { to: '/app/bot', label: 'nav.bot' as const, end: false },
  { to: '/app/settings', label: 'nav.settings' as const, end: false },
];

/** Authenticated product shell: sticky header, pill nav, language + sign-out. */
export function AppShell() {
  const t = useT();
  const { lang, setLang } = useI18n();
  const me = useMe();
  const signOut = useSignOut();

  return (
    <div className={s.wrap}>
      <a className={s.skip} href="#main">
        {lang === 'es' ? 'Saltar al contenido' : 'Skip to content'}
      </a>
      <header className={s.header}>
        <div className={s.headerInner}>
          <NavLink to="/app" className={s.brand} end>
            <span className={s.brandDot} aria-hidden />
            {t('brand.name')}
          </NavLink>
          {API_MODE === 'mock' && <span className={s.mockTag}>{t('app.mock')}</span>}
          <nav className={s.nav} aria-label="Main">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end}>
                {t(n.label)}
              </NavLink>
            ))}
          </nav>
          <span className={s.spacer} />
          <div className={s.actions}>
            {me.data && (
              <span className={s.orgChip}>
                <strong>{me.data.memberships[0]?.organization_name}</strong>
              </span>
            )}
            <button
              type="button"
              className={s.langBtn}
              onClick={() => setLang(lang === 'es' ? 'en' : 'es')}
              lang={lang === 'es' ? 'en' : 'es'}
            >
              {lang === 'es' ? 'EN' : 'ES'}
            </button>
            <button type="button" className={`secondary ${s.exitBtn}`} onClick={signOut}>
              {t('app.exit')}
            </button>
          </div>
        </div>
      </header>
      <main id="main" className={s.main}>
        <div className={s.inner}>
          <Suspense fallback={<p className="muted">{t('common.loading')}</p>}>
            <Outlet />
          </Suspense>
        </div>
      </main>
    </div>
  );
}
