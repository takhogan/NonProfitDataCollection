import { lazy } from 'react';
import { Navigate, type RouteObject } from 'react-router';
import { AppShell } from './shell/AppShell';
import { RequireAuth } from './shell/RequireAuth';

// Each page is its own chunk.
const LandingPage = lazy(() => import('./pages/LandingPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const SignupPage = lazy(() => import('./pages/SignupPage'));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const DataPage = lazy(() => import('./pages/DataPage'));
const ReportDetailPage = lazy(() => import('./pages/ReportDetailPage'));
const CampaignsPage = lazy(() => import('./pages/CampaignsPage'));
const BotEditorPage = lazy(() => import('./pages/BotEditorPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));

export const productRoutes: RouteObject[] = [
  { path: '/', element: <LandingPage /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/signup', element: <SignupPage /> },
  {
    path: '/onboarding',
    element: (
      <RequireAuth>
        <OnboardingPage />
      </RequireAuth>
    ),
  },
  {
    path: '/app',
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'data', element: <DataPage /> },
      // Old /reports list is replaced by Data; the detail route stays so the
      // drawer's "open full view" and any deep links keep working.
      { path: 'reports', element: <Navigate to="/app/data" replace /> },
      { path: 'reports/:reportId', element: <ReportDetailPage /> },
      { path: 'campaigns', element: <CampaignsPage /> },
      { path: 'bot', element: <BotEditorPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
];
