import { lazy, Suspense } from 'react';
import { NavLink, Outlet } from 'react-router';
import { API_MODE } from '../api';
import { useMe } from '../api/queries';
import { useI18n } from '../locales/i18n';
import { Loading, QueryError } from '../ui/common';
import { navFor } from './nav';
import { useQuickExit } from './session';
import { StatusBanner } from './StatusBanner';
import s from './Layout.module.css';

// Dev-only: the condition is statically false in production builds, so the
// switcher (and the mock controls it imports) are dropped from the bundle.
const DevRoleSwitcher =
  import.meta.env.DEV && API_MODE === 'mock' ? lazy(() => import('./dev/DevRoleSwitcher')) : null;

export function Layout() {
  const { t, lang, setLang } = useI18n();
  const me = useMe();
  const exit = useQuickExit();

  return (
    <>
      <a className={s.skip} href="#main">
        {t('common.skipToContent')}
      </a>
      <header className={s.header}>
        <div className={s.headerTop}>
          <span className={s.brand}>
            {t('app.title')} {API_MODE === 'mock' && <span className={s.mockTag}>{t('app.syntheticData')}</span>}
          </span>
          <div className={s.headerActions}>
            <button type="button" onClick={() => setLang(lang === 'es' ? 'en' : 'es')} lang={lang === 'es' ? 'en' : 'es'}>
              {lang === 'es' ? 'English' : 'Español'}
            </button>
            <button type="button" className={s.exit} onClick={exit}>
              {t('app.exit')}
            </button>
          </div>
        </div>
        {me.data && (
          <div className={s.context} aria-label={t('app.contextLabel')}>
            <span>
              {t('app.org')}: <strong>{me.data.tenant.name}</strong>
            </span>
            {me.data.provider_organization && (
              <span>
                {t('app.provider')}: <strong>{me.data.provider_organization.name}</strong> (
                {t(`vetting.${me.data.provider_organization.vetting_status}`)})
              </span>
            )}
            <span>
              {t('app.role')}: <strong>{me.data.roles.map((r) => t(`role.${r}`)).join(', ')}</strong>
            </span>
          </div>
        )}
      </header>
      {me.data && (
        <nav className={s.nav} aria-label={t('app.navLabel')}>
          <ul>
            {navFor(me.data.roles).map((item) => (
              <li key={item.path}>
                <NavLink to={item.path} end>
                  {t(item.label)}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      )}
      <StatusBanner />
      <main id="main" className={s.main}>
        {me.isPending ? (
          <Loading />
        ) : me.isError ? (
          <QueryError error={me.error} onRetry={() => me.refetch()} />
        ) : (
          <Suspense fallback={<Loading />}>
            <Outlet />
          </Suspense>
        )}
      </main>
      {DevRoleSwitcher && (
        <Suspense fallback={null}>
          <DevRoleSwitcher />
        </Suspense>
      )}
    </>
  );
}
