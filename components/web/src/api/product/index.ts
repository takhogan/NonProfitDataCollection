/**
 * Entry point for the Dashboard API client. One env switch moves the whole app
 * between fake data and the real backend:
 *
 *   # mock (default)
 *   npm run dev
 *   # local uvicorn
 *   VITE_API_MODE=http VITE_API_BASE_URL=http://localhost:8001 npm run dev
 *   # Cloud Run
 *   VITE_API_MODE=http VITE_API_BASE_URL=https://<service>.run.app npm run dev
 */
import type { ProductApiClient } from './client';
import { HttpProductClient } from './http';
import { MockProductClient } from './mock';

export type { ProductApiClient, ReportStatus } from './client';
export { ProductApiError } from './client';
export { clearToken, getToken, setToken } from './token';
export * from '../generated';

export const API_MODE: 'mock' | 'http' = import.meta.env.VITE_API_MODE === 'http' ? 'http' : 'mock';
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001';

export function createProductClient(): ProductApiClient {
  if (API_MODE === 'http') return new HttpProductClient(API_BASE_URL);
  return new MockProductClient();
}
