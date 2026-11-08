import type { Role } from '../api';
import type { MessageKey } from '../locales/es';

export interface NavItem {
  path: string;
  label: MessageKey;
  roles: Role[];
}

const AGGREGATE_ROLES: Role[] = ['provider', 'coordinator', 'analyst', 'org_admin'];

/** WEB-001: navigation shows only what the role allows (presentation only; the API authorizes). */
export const NAV: NavItem[] = [
  { path: '/areas', label: 'nav.areasOfNeed', roles: AGGREGATE_ROLES },
  { path: '/coverage', label: 'nav.coverage', roles: AGGREGATE_ROLES },
  { path: '/activities', label: 'nav.myActivities', roles: ['provider'] },
  { path: '/activities/new', label: 'nav.logActivity', roles: ['provider'] },
  { path: '/alerts', label: 'nav.alerts', roles: ['provider'] },
  { path: '/data-health', label: 'nav.dataHealth', roles: ['coordinator'] },
  { path: '/review', label: 'nav.review', roles: ['reviewer'] },
  { path: '/intake/new', label: 'nav.intake', roles: ['intake_volunteer'] },
  { path: '/indicators', label: 'nav.indicators', roles: ['analyst'] },
  { path: '/admin', label: 'nav.admin', roles: ['org_admin'] },
];

/** WEB-002: each role lands on its main view. Order decides for multi-role users. */
const HOME: [Role, string][] = [
  ['provider', '/areas'],
  ['coordinator', '/data-health'],
  ['reviewer', '/review'],
  ['intake_volunteer', '/intake/new'],
  ['analyst', '/indicators'],
  ['org_admin', '/admin'],
];

export function homeFor(roles: Role[]): string {
  return HOME.find(([r]) => roles.includes(r))?.[1] ?? '/no-access';
}

export function navFor(roles: Role[]): NavItem[] {
  return NAV.filter((i) => i.roles.some((r) => roles.includes(r)));
}

export function canAccess(path: string, roles: Role[]): boolean {
  const item = NAV.find((i) => i.path === path);
  return !item || item.roles.some((r) => roles.includes(r));
}
