import { createContext, useContext, type ReactNode } from 'react';
import type { ProductApiClient } from './client';

const Ctx = createContext<ProductApiClient | null>(null);

export function ProductApiProvider({ client, children }: { client: ProductApiClient; children: ReactNode }) {
  return <Ctx.Provider value={client}>{children}</Ctx.Provider>;
}

export function useProductApi(): ProductApiClient {
  const c = useContext(Ctx);
  if (!c) throw new Error('useProductApi outside ProductApiProvider');
  return c;
}
