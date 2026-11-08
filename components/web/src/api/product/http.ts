import type {
  AreaCount,
  AskRequest,
  AskResponse,
  BotConfig,
  Campaign,
  CampaignCreate,
  ChannelsConfig,
  CollectionTemplate,
  Contact,
  ContactImportResult,
  DashboardConfig,
  DashboardSummary,
  DashboardTemplate,
  DataProtectionConfig,
  FeedResponse,
  LoginRequest,
  MeResponse,
  OrgProfile,
  RecommendedTemplates,
  ReportDetail,
  ReportPatch,
  ReportSummary,
  SignupRequest,
  SuggestFieldsRequest,
  SuggestFieldsResponse,
  TokenResponse,
} from '../generated';
import type { ApiErrorBody, ProductApiClient, ReportStatus } from './client';
import { ProductApiError } from './client';
import { getToken, setToken } from './token';

/**
 * Real client for the FastAPI Dashboard API. Base URL from
 * `VITE_API_BASE_URL` (e.g. http://localhost:8001 or the Cloud Run URL). Sends
 * the JWT as a bearer token; on auth success it stores the token.
 */
export class HttpProductClient implements ProductApiClient {
  private readonly baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    let res: Response;
    try {
      const isForm = body instanceof FormData;
      if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
      res = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      });
    } catch {
      throw new ProductApiError({ code: 'network_error', message: 'Cannot reach the server.' }, 0);
    }
    if (res.status === 204) return undefined as T;
    const json: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      const envelope = (json as { error?: ApiErrorBody } | null)?.error;
      throw new ProductApiError(
        envelope ?? { code: res.status === 403 ? 'permission_denied' : 'internal', message: 'Request failed.' },
        res.status,
      );
    }
    return json as T;
  }

  // Auth
  async signup(b: SignupRequest) {
    const r = await this.request<TokenResponse>('POST', '/auth/signup', b);
    setToken(r.access_token);
    return r;
  }
  async login(b: LoginRequest) {
    const r = await this.request<TokenResponse>('POST', '/auth/login', b);
    setToken(r.access_token);
    return r;
  }
  getMe() {
    return this.request<MeResponse>('GET', '/me');
  }

  // Org profile & onboarding
  getOrgProfile() {
    return this.request<OrgProfile>('GET', '/org/profile');
  }
  putOrgProfile(b: OrgProfile) {
    return this.request<OrgProfile>('PUT', '/org/profile', b);
  }
  getCollectionTemplates() {
    return this.request<CollectionTemplate[]>('GET', '/templates/collection');
  }
  getRecommendedCollection() {
    return this.request<RecommendedTemplates>('GET', '/templates/collection/recommended');
  }
  getDashboardTemplates() {
    return this.request<DashboardTemplate[]>('GET', '/templates/dashboard');
  }
  putBotConfig(b: BotConfig) {
    return this.request<BotConfig>('PUT', '/org/bot-config', b);
  }
  putDashboardConfig(b: DashboardConfig) {
    return this.request<DashboardConfig>('PUT', '/org/dashboard-config', b);
  }

  // Data protection
  getDataProtection() {
    return this.request<DataProtectionConfig>('GET', '/org/data-protection');
  }
  putDataProtection(b: DataProtectionConfig) {
    return this.request<DataProtectionConfig>('PUT', '/org/data-protection', b);
  }

  // Channels
  getChannels() {
    return this.request<ChannelsConfig>('GET', '/org/channels');
  }
  putChannels(b: ChannelsConfig) {
    return this.request<ChannelsConfig>('PUT', '/org/channels', b);
  }

  // Contacts
  importContacts(file: File) {
    const fd = new FormData();
    fd.append('file', file);
    return this.request<ContactImportResult>('POST', '/contacts/import', fd);
  }
  getContacts() {
    return this.request<Contact[]>('GET', '/contacts');
  }

  // Dashboard
  getDashboardSummary() {
    return this.request<DashboardSummary>('GET', '/dashboard/summary');
  }
  getDashboardAreas() {
    return this.request<AreaCount[]>('GET', '/dashboard/areas');
  }
  getFeed(since?: string) {
    const q = since ? `?since=${encodeURIComponent(since)}` : '';
    return this.request<FeedResponse>('GET', `/dashboard/feed${q}`);
  }

  // Reports
  getReports(status?: ReportStatus) {
    const q = status ? `?status=${encodeURIComponent(status)}` : '';
    return this.request<ReportSummary[]>('GET', `/reports${q}`);
  }
  getReport(id: string) {
    return this.request<ReportDetail>('GET', `/reports/${encodeURIComponent(id)}`);
  }
  patchReport(id: string, b: ReportPatch) {
    return this.request<ReportDetail>('PATCH', `/reports/${encodeURIComponent(id)}`, b);
  }

  // Campaigns
  getCampaigns() {
    return this.request<Campaign[]>('GET', '/campaigns');
  }
  createCampaign(b: CampaignCreate) {
    return this.request<Campaign>('POST', '/campaigns', b);
  }
  suggestCampaignFields(b: SuggestFieldsRequest) {
    return this.request<SuggestFieldsResponse>('POST', '/campaigns/suggest-fields', b);
  }

  // Ask
  ask(b: AskRequest) {
    return this.request<AskResponse>('POST', '/ask', b);
  }
}
