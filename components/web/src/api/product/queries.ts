/**
 * TanStack Query hooks over the Dashboard API. Query keys are prefixed `p` to
 * keep them separate from the legacy provider-portal caches.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useProductApi } from './context';
import type { ReportStatus } from './client';
import type {
  BotConfig,
  CampaignCreate,
  ChannelsConfig,
  DashboardConfig,
  DataProtectionConfig,
  OrgProfile,
  ReportPatch,
} from '../generated';

export function useMe() {
  const api = useProductApi();
  return useQuery({ queryKey: ['p', 'me'], queryFn: () => api.getMe(), staleTime: 5 * 60_000, retry: false });
}

export function useOrgProfile() {
  const api = useProductApi();
  return useQuery({ queryKey: ['p', 'org-profile'], queryFn: () => api.getOrgProfile() });
}

export function useCollectionTemplates() {
  const api = useProductApi();
  return useQuery({ queryKey: ['p', 'templates', 'collection'], queryFn: () => api.getCollectionTemplates(), staleTime: Infinity });
}

export function useRecommendedCollection() {
  const api = useProductApi();
  return useQuery({ queryKey: ['p', 'templates', 'collection', 'recommended'], queryFn: () => api.getRecommendedCollection(), staleTime: Infinity });
}

export function useDashboardTemplates() {
  const api = useProductApi();
  return useQuery({ queryKey: ['p', 'templates', 'dashboard'], queryFn: () => api.getDashboardTemplates(), staleTime: Infinity });
}

export function useDataProtection() {
  const api = useProductApi();
  return useQuery({ queryKey: ['p', 'data-protection'], queryFn: () => api.getDataProtection() });
}

export function useChannels() {
  const api = useProductApi();
  return useQuery({ queryKey: ['p', 'channels'], queryFn: () => api.getChannels() });
}

export function useContacts() {
  const api = useProductApi();
  return useQuery({ queryKey: ['p', 'contacts'], queryFn: () => api.getContacts() });
}

export function useDashboardSummary() {
  const api = useProductApi();
  return useQuery({ queryKey: ['p', 'dashboard', 'summary'], queryFn: () => api.getDashboardSummary(), refetchInterval: 30_000 });
}

export function useDashboardAreas() {
  const api = useProductApi();
  return useQuery({ queryKey: ['p', 'dashboard', 'areas'], queryFn: () => api.getDashboardAreas(), refetchInterval: 60_000 });
}

export function useReports(status?: ReportStatus) {
  const api = useProductApi();
  return useQuery({ queryKey: ['p', 'reports', status ?? 'all'], queryFn: () => api.getReports(status) });
}

export function useReport(id: string) {
  const api = useProductApi();
  return useQuery({ queryKey: ['p', 'report', id], queryFn: () => api.getReport(id), enabled: !!id });
}

export function useCampaigns() {
  const api = useProductApi();
  return useQuery({ queryKey: ['p', 'campaigns'], queryFn: () => api.getCampaigns() });
}

// ---- Mutations ----

export function usePutOrgProfile() {
  const api = useProductApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: OrgProfile) => api.putOrgProfile(b),
    onSuccess: (data) => {
      qc.setQueryData(['p', 'org-profile'], data);
      qc.invalidateQueries({ queryKey: ['p', 'me'] });
    },
  });
}

export function usePutBotConfig() {
  const api = useProductApi();
  return useMutation({ mutationFn: (b: BotConfig) => api.putBotConfig(b) });
}

export function usePutDashboardConfig() {
  const api = useProductApi();
  return useMutation({ mutationFn: (b: DashboardConfig) => api.putDashboardConfig(b) });
}

export function usePutDataProtection() {
  const api = useProductApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: DataProtectionConfig) => api.putDataProtection(b),
    onSuccess: (data) => {
      qc.setQueryData(['p', 'data-protection'], data);
      // Personal-field visibility changed: refetch anything that carries it.
      qc.invalidateQueries({ queryKey: ['p', 'reports'] });
      qc.invalidateQueries({ queryKey: ['p', 'contacts'] });
    },
  });
}

export function usePutChannels() {
  const api = useProductApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: ChannelsConfig) => api.putChannels(b),
    onSuccess: (data) => qc.setQueryData(['p', 'channels'], data),
  });
}

export function useImportContacts() {
  const api = useProductApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.importContacts(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['p', 'contacts'] }),
  });
}

export function usePatchReport() {
  const api = useProductApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ReportPatch }) => api.patchReport(id, body),
    onSuccess: (data) => {
      qc.setQueryData(['p', 'report', data.id], data);
      qc.invalidateQueries({ queryKey: ['p', 'reports'] });
    },
  });
}

export function useCreateCampaign() {
  const api = useProductApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: CampaignCreate) => api.createCampaign(b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['p', 'campaigns'] }),
  });
}

export function useAsk() {
  const api = useProductApi();
  return useMutation({ mutationFn: (question: string) => api.ask({ question }) });
}
