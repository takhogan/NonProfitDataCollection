/**
 * Public entry point of the API layer. Everything outside `src/api` imports
 * from here.
 *
 * Swapping the mock for the real backend is one setting:
 *     VITE_API_MODE=http VITE_API_BASE_URL=https://api.example.org npm run dev
 * (or put those lines in `.env.local`). The default is `mock`.
 */
import type { ApiClient } from './client';
import { HttpApiClient } from './http';
import { MockApiClient } from './mock/mockClient';

export type * from './schema';
export type { ApiClient, AreasOfNeedQuery, CoverageQuery, IndicatorQuery } from './client';
export { ApiError, newOperationKey } from './client';
export { MockApiClient } from './mock/mockClient';
export type { DevIdentity, SimulatedStatus } from './mock/mockClient';

export const API_MODE: 'mock' | 'http' = import.meta.env.VITE_API_MODE === 'http' ? 'http' : 'mock';

export function createApiClient(): ApiClient {
  if (API_MODE === 'http') {
    return new HttpApiClient(import.meta.env.VITE_API_BASE_URL ?? '');
  }
  return new MockApiClient();
}
