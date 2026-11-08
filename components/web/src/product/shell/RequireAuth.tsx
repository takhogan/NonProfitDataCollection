import type { ReactNode } from 'react';
import { Navigate } from 'react-router';
import { useMe } from '../../api/product/queries';
import { useT } from '../i18n';
import { hasToken } from './session';

/** Gate for authenticated pages. No token → landing. Token but `/me` fails → login. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const t = useT();
  const me = useMe();

  if (!hasToken()) return <Navigate to="/" replace />;
  if (me.isPending) return <p className="muted">{t('common.loading')}</p>;
  if (me.isError) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
