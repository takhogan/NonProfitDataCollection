/**
 * TanStack Query hooks. Every key starts with the organization context
 * (tenant + provider org) so caches never mix organizations (README:
 * "Include organization context in cache keys").
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from './context';
import type { AreasOfNeedQuery, CoverageQuery, IndicatorQuery } from './client';
import type {
  ActivityCreate,
  ActivityQuery,
  ActivityUpdate,
  AlertSubscriptionCreate,
  Me,
  UUID,
} from './schema';

export function orgKey(me: Me | undefined): string {
  return me ? `${me.tenant.id}:${me.provider_organization?.id ?? '-'}` : 'anon';
}

export function useMe() {
  const api = useApi();
  return useQuery({ queryKey: ['me'], queryFn: () => api.getMe(), staleTime: 5 * 60_000 });
}

/** The org-scoped key prefix; queries wait until `me` is known. */
function useOrg() {
  const me = useMe();
  return { org: orgKey(me.data), ready: me.isSuccess };
}

export function useStatus() {
  const api = useApi();
  const { org, ready } = useOrg();
  return useQuery({
    queryKey: [org, 'status'],
    queryFn: () => api.getStatus(),
    enabled: ready,
    refetchInterval: 60_000,
  });
}

export function useAreas() {
  const api = useApi();
  const { org, ready } = useOrg();
  return useQuery({ queryKey: [org, 'areas'], queryFn: () => api.listAreas(), enabled: ready, staleTime: 10 * 60_000 });
}

export function useMeetingPoints(sectorIds: UUID[]) {
  const api = useApi();
  const { org, ready } = useOrg();
  return useQuery({
    queryKey: [org, 'meeting-points', [...sectorIds].sort()],
    queryFn: () => api.listMeetingPoints(sectorIds),
    enabled: ready && sectorIds.length > 0,
  });
}

export function useIndicators(q: IndicatorQuery) {
  const api = useApi();
  const { org, ready } = useOrg();
  return useQuery({ queryKey: [org, 'indicators', q], queryFn: () => api.getIndicators(q), enabled: ready });
}

export function useAreasOfNeed(q: AreasOfNeedQuery) {
  const api = useApi();
  const { org, ready } = useOrg();
  return useQuery({ queryKey: [org, 'areas-of-need', q], queryFn: () => api.getAreasOfNeed(q), enabled: ready });
}

export function useCoverage(q: CoverageQuery, enabled = true) {
  const api = useApi();
  const { org, ready } = useOrg();
  return useQuery({ queryKey: [org, 'coverage', q], queryFn: () => api.getCoverage(q), enabled: ready && enabled });
}

export function useAreaDetail(id: UUID) {
  const api = useApi();
  const { org, ready } = useOrg();
  return useQuery({ queryKey: [org, 'area', id], queryFn: () => api.getAreaDetail(id), enabled: ready });
}

export function useActivities(q: ActivityQuery = {}) {
  const api = useApi();
  const { org, ready } = useOrg();
  return useQuery({ queryKey: [org, 'activities', q], queryFn: () => api.listActivities(q), enabled: ready });
}

/** Activity writes change coverage, area detail and activity lists. */
function useInvalidateActivityViews() {
  const qc = useQueryClient();
  const { org } = useOrg();
  return () =>
    Promise.all(
      ['activities', 'coverage', 'area', 'areas-of-need'].map((k) =>
        qc.invalidateQueries({ queryKey: [org, k] }),
      ),
    );
}

export function useCreateActivity() {
  const api = useApi();
  const invalidate = useInvalidateActivityViews();
  return useMutation({ mutationFn: (cmd: ActivityCreate) => api.createActivity(cmd), onSuccess: invalidate });
}

export function useUpdateActivity() {
  const api = useApi();
  const invalidate = useInvalidateActivityViews();
  return useMutation({
    mutationFn: ({ id, cmd }: { id: UUID; cmd: ActivityUpdate }) => api.updateActivity(id, cmd),
    onSuccess: invalidate,
  });
}

export function useConfirmActivity() {
  const api = useApi();
  const invalidate = useInvalidateActivityViews();
  return useMutation({
    mutationFn: ({ id, operationKey }: { id: UUID; operationKey: string }) => api.confirmActivity(id, operationKey),
    onSuccess: invalidate,
  });
}

export function useAlertSubscriptions() {
  const api = useApi();
  const { org, ready } = useOrg();
  return useQuery({ queryKey: [org, 'alert-subscriptions'], queryFn: () => api.listAlertSubscriptions(), enabled: ready });
}

export function useAlerts() {
  const api = useApi();
  const { org, ready } = useOrg();
  return useQuery({ queryKey: [org, 'alerts'], queryFn: () => api.listAlerts(), enabled: ready });
}

function useInvalidateSubscriptions() {
  const qc = useQueryClient();
  const { org } = useOrg();
  return () => qc.invalidateQueries({ queryKey: [org, 'alert-subscriptions'] });
}

export function useCreateAlertSubscription() {
  const api = useApi();
  const invalidate = useInvalidateSubscriptions();
  return useMutation({ mutationFn: (cmd: AlertSubscriptionCreate) => api.createAlertSubscription(cmd), onSuccess: invalidate });
}

export function useMuteAlertSubscription() {
  const api = useApi();
  const invalidate = useInvalidateSubscriptions();
  return useMutation({
    mutationFn: ({ id, muted }: { id: UUID; muted: boolean }) => api.setAlertSubscriptionMuted(id, muted),
    onSuccess: invalidate,
  });
}

export function useDeleteAlertSubscription() {
  const api = useApi();
  const invalidate = useInvalidateSubscriptions();
  return useMutation({ mutationFn: (id: UUID) => api.deleteAlertSubscription(id), onSuccess: invalidate });
}
