import type { ReactNode } from 'react';
import type { Role } from '../api';
import { useMe } from '../api/queries';
import { useI18n } from '../locales/i18n';
import { Loading } from '../ui/common';

/** Presentation-only guard (README: client-side role checks are not authorization). */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const me = useMe();
  const { t } = useI18n();
  if (!me.data) return <Loading />;
  if (!roles.some((r) => me.data.roles.includes(r))) {
    return (
      <>
        <h1>{t('noAccess.title')}</h1>
        <p>{t('noAccess.body')}</p>
      </>
    );
  }
  return <>{children}</>;
}
