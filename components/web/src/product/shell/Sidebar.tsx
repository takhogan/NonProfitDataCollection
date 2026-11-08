import { NavLink } from 'react-router';
import {
  LayoutDashboard,
  Table2,
  Megaphone,
  MessageSquareText,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  LogOut,
  X,
} from 'lucide-react';
import { useMe } from '../../api/product/queries';
import { useI18n } from '../../locales/i18n';
import { useT, type ProductKey } from '../i18n';
import { useSignOut } from './session';
import { LiveDot } from '../../ui/kit';
import { PrivacyBadge } from '../components/PrivacyBadge';
import s from './Sidebar.module.css';

const NAV = [
  { to: '/app', label: 'nav.dashboard' as ProductKey, icon: LayoutDashboard, end: true },
  { to: '/app/data', label: 'nav.data' as ProductKey, icon: Table2, end: false },
  { to: '/app/campaigns', label: 'nav.campaigns' as ProductKey, icon: Megaphone, end: false },
  { to: '/app/bot', label: 'nav.bot' as ProductKey, icon: MessageSquareText, end: false },
  { to: '/app/settings', label: 'nav.settings' as ProductKey, icon: Settings, end: false },
];

export function Sidebar({
  collapsed,
  onToggleCollapsed,
  mobileOpen,
  onCloseMobile,
}: {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const t = useT();
  const { lang, setLang } = useI18n();
  const me = useMe();
  const signOut = useSignOut();

  const cls = [s.sidebar, collapsed ? s.collapsed : '', mobileOpen ? s.mobileOpen : ''].filter(Boolean).join(' ');

  return (
    <>
      {mobileOpen && <div className={s.scrim} onClick={onCloseMobile} aria-hidden />}
      <aside className={cls} aria-label={lang === 'es' ? 'Navegación' : 'Navigation'}>
        <div className={s.top}>
          <NavLink to="/app" className={s.brand} end onClick={onCloseMobile}>
            {collapsed ? 'M' : t('brand.name')}
          </NavLink>
          <button type="button" className={`${s.iconBtn} ${s.collapseBtn}`} onClick={onToggleCollapsed} aria-label={collapsed ? 'Expand' : 'Collapse'} title={collapsed ? 'Expand' : 'Collapse'}>
            {collapsed ? <PanelLeftOpen size={18} strokeWidth={1.5} /> : <PanelLeftClose size={18} strokeWidth={1.5} />}
          </button>
          <button type="button" className={`${s.iconBtn} ${s.mobileClose}`} onClick={onCloseMobile} aria-label="Close">
            <X size={20} strokeWidth={1.5} />
          </button>
        </div>

        <nav className={s.nav}>
          {NAV.map((n) => {
            const Icon = n.icon;
            return (
              <NavLink key={n.to} to={n.to} end={n.end} className={s.navItem} onClick={onCloseMobile} title={collapsed ? t(n.label) : undefined}>
                <Icon size={19} strokeWidth={1.6} className={s.navIcon} />
                <span className={s.navLabel}>{t(n.label)}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className={s.footer}>
          {me.data && (
            <div className={s.org} title={me.data.memberships[0]?.organization_name}>
              <span className={s.orgInitial}>{(me.data.memberships[0]?.organization_name ?? 'M').slice(0, 1)}</span>
              <span className={s.orgName}>{me.data.memberships[0]?.organization_name}</span>
            </div>
          )}
          <div className={s.status}>
            <LiveDot label={collapsed ? '' : t('dashboard.listening')} />
          </div>
          <div className={s.badge}>
            <PrivacyBadge />
          </div>
          <div className={s.footActions}>
            <button type="button" className={s.footBtn} onClick={() => setLang(lang === 'es' ? 'en' : 'es')} lang={lang === 'es' ? 'en' : 'es'} title={lang === 'es' ? 'English' : 'Español'}>
              <span className={s.footBtnIcon}>{lang === 'es' ? 'EN' : 'ES'}</span>
              <span className={s.navLabel}>{lang === 'es' ? 'English' : 'Español'}</span>
            </button>
            <button type="button" className={s.footBtn} onClick={signOut} title={t('app.exit')}>
              <LogOut size={17} strokeWidth={1.6} className={s.footBtnIcon} />
              <span className={s.navLabel}>{t('app.exit')}</span>
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
