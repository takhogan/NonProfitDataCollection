import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { ApiClient } from '../api';
import { ApiProvider } from '../api/context';
import { I18nProvider, type Lang } from '../locales/i18n';

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: 1,
        // Low bandwidth (NFR-03): no refetch storm on tab focus.
        refetchOnWindowFocus: false,
      },
      // WEB-005: never auto-retry writes; the user retries with the same operation key.
      mutations: { retry: 0 },
    },
  });
}

export function AppProviders({
  client,
  queryClient,
  lang,
  children,
}: {
  client: ApiClient;
  queryClient: QueryClient;
  lang?: Lang;
  children: ReactNode;
}) {
  return (
    <ApiProvider client={client}>
      <QueryClientProvider client={queryClient}>
        <I18nProvider initial={lang}>{children}</I18nProvider>
      </QueryClientProvider>
    </ApiProvider>
  );
}
