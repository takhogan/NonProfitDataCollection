import { lazy } from 'react';
import { Navigate, type RouteObject } from 'react-router';
import { useMe } from '../api/queries';
import { Loading } from '../ui/common';
import { Layout } from './Layout';
import { homeFor } from './nav';
import { RequireRole } from './RequireRole';
import type { Role } from '../api';
import type { ReactNode } from 'react';

// WEB-006: every page is its own chunk.
const AreasOfNeedPage = lazy(() => import('../features/areas/AreasOfNeedPage'));
const AreaDetailPage = lazy(() => import('../features/areas/AreaDetailPage'));
const CoveragePage = lazy(() => import('../features/coverage/CoveragePage'));
const MyActivitiesPage = lazy(() => import('../features/activities/MyActivitiesPage'));
const LogActivityPage = lazy(() => import('../features/activities/LogActivityPage'));
const AlertsPage = lazy(() => import('../features/alerts/AlertsPage'));
const PlaceholderPage = lazy(() => import('../features/placeholders/PlaceholderPage'));
const SignedOutPage = lazy(() => import('../features/placeholders/SignedOutPage'));

function RoleHome() {
  const me = useMe();
  if (!me.data) return <Loading />;
  return <Navigate to={homeFor(me.data.roles)} replace />;
}

const AGG: Role[] = ['provider', 'coordinator', 'analyst', 'org_admin'];
const guard = (roles: Role[], el: ReactNode) => <RequireRole roles={roles}>{el}</RequireRole>;

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <RoleHome /> },
      { path: 'areas', element: guard(AGG, <AreasOfNeedPage />) },
      { path: 'areas/:areaId', element: guard(AGG, <AreaDetailPage />) },
      { path: 'coverage', element: guard(AGG, <CoveragePage />) },
      { path: 'activities', element: guard(['provider'], <MyActivitiesPage />) },
      { path: 'activities/new', element: guard(['provider'], <LogActivityPage />) },
      { path: 'alerts', element: guard(['provider'], <AlertsPage />) },
      { path: 'data-health', element: guard(['coordinator'], <PlaceholderPage title="nav.dataHealth" req="WEB-033" />) },
      { path: 'review', element: guard(['reviewer'], <PlaceholderPage title="nav.review" req="WEB-036" />) },
      { path: 'intake/new', element: guard(['intake_volunteer'], <PlaceholderPage title="nav.intake" req="WEB-030" />) },
      { path: 'indicators', element: guard(['analyst'], <PlaceholderPage title="nav.indicators" req="WEB-002" />) },
      { path: 'admin', element: guard(['org_admin'], <PlaceholderPage title="nav.admin" req="WEB-040, WEB-041" />) },
      { path: 'no-access', element: <PlaceholderPage title="noAccess.title" /> },
      { path: '*', element: <PlaceholderPage title="notFound.title" /> },
    ],
  },
  { path: '/signed-out', element: <SignedOutPage /> },
];
