import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { ProductApiClient } from '../api/product';
import { ProductApiProvider } from '../api/product/context';
import { I18nProvider, type Lang } from '../locales/i18n';

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, gcTime: 5 * 60_000, retry: 1, refetchOnWindowFocus: false },
      mutations: { retry: 0 },
    },
  });
}

export function ProductProviders({
  client,
  queryClient,
  lang,
  children,
}: {
  client: ProductApiClient;
  queryClient: QueryClient;
  lang?: Lang;
  children: ReactNode;
}) {
  return (
    <ProductApiProvider client={client}>
      <QueryClientProvider client={queryClient}>
        <I18nProvider initial={lang}>{children}</I18nProvider>
      </QueryClientProvider>
    </ProductApiProvider>
  );
}
