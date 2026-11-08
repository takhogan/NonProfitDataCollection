import { lazy } from 'react';
import type { RouteObject } from 'react-router';
import { AppShell } from './shell/AppShell';
import { RequireAuth } from './shell/RequireAuth';

// Each page is its own chunk.
const LandingPage = lazy(() => import('./pages/LandingPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const SignupPage = lazy(() => import('./pages/SignupPage'));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const ReportsPage = lazy(() => import('./pages/ReportsPage'));
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
      { path: 'reports', element: <ReportsPage /> },
      { path: 'reports/:reportId', element: <ReportDetailPage /> },
      { path: 'campaigns', element: <CampaignsPage /> },
      { path: 'bot', element: <BotEditorPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
];
