import { useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { useNavigate } from 'react-router';
import { clearToken, getToken } from '../../api/product';
import { resetMockState } from '../../api/product/mock';

/** True when a bearer token is present (optimistic; `/me` is the real check). */
export function hasToken(): boolean {
  return !!getToken();
}

/** Sign out: drop the token and every cached response, then go to the landing page. */
export function useSignOut() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  return useCallback(() => {
    clearToken();
    resetMockState();
    qc.cancelQueries();
    qc.clear();
    navigate('/', { replace: true });
  }, [qc, navigate]);
}
