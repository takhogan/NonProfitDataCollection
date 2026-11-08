import { Suspense, useState } from 'react';
import { Outlet } from 'react-router';
import { Menu } from 'lucide-react';
import { useI18n } from '../../locales/i18n';
import { useT } from '../i18n';
import { Sidebar } from './Sidebar';
import { useLocalState } from './useLocalState';
import s from './AppShell.module.css';

/** Authenticated product shell: collapsible sidebar + content area. */
export function AppShell() {
  const t = useT();
  const { lang } = useI18n();
  // v2 key so any previously-persisted collapsed=true is ignored; expanded is the default.
  const [collapsed, setCollapsed] = useLocalState<boolean>('metron.sidebar.collapsed.v2', false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className={s.wrap}>
      <a className={s.skip} href="#main">
        {lang === 'es' ? 'Saltar al contenido' : 'Skip to content'}
      </a>
      <Sidebar
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed(!collapsed)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div
        className={s.content}
        style={{ ['--content-left' as string]: collapsed ? '60px' : '236px' }}
      >
        {/* Mobile top bar: just a menu button; everything else lives in the drawer. */}
        <div className={s.mobileBar}>
          <button type="button" className={s.menuBtn} onClick={() => setMobileOpen(true)} aria-label="Menu">
            <Menu size={22} strokeWidth={1.6} />
          </button>
          <span className={s.mobileBrand}>{t('brand.name')}</span>
        </div>
        <main id="main" className={s.main}>
          <Suspense fallback={<p className="muted">{t('common.loading')}</p>}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
