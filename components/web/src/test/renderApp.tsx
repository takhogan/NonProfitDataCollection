import { render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { MockApiClient } from '../api';
import { AppProviders, createQueryClient } from '../app/AppProviders';
import { routes } from '../app/routes';
import type { Lang } from '../locales/i18n';

export const FIXED_NOW = Date.parse('2026-11-07T16:00:00Z');

export function renderApp(path: string, opts: { client?: MockApiClient; lang?: Lang } = {}) {
  const client = opts.client ?? new MockApiClient({ now: FIXED_NOW, latencyMs: 0 });
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false, staleTime: 0 } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const utils = render(
    <AppProviders client={client} queryClient={queryClient} lang={opts.lang}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...utils, client, router, queryClient };
}
