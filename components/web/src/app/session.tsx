import { useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { useNavigate } from 'react-router';

/**
 * WEB-060/062: "Salir" drops every cached response from memory before leaving.
 * With the real API this will also call the logout endpoint; the session
 * cookie is HttpOnly, so the client cannot clear it itself.
 */
export function useQuickExit() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  return useCallback(() => {
    qc.cancelQueries();
    qc.clear();
    navigate('/signed-out', { replace: true });
  }, [qc, navigate]);
}
