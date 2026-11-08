/**
 * The Dashboard API (`components/api`, CONTRACT.md v0.1) as a typed interface.
 * Two implementations:
 *   - `HttpProductClient` — talks to the FastAPI service (JWT bearer).
 *   - `MockProductClient` — in-memory fake data matching the contract exactly.
 *
 * The web app picks one via `VITE_API_MODE` (see `product/index.ts`), so the
 * same UI runs against mock → local uvicorn → Cloud Run with one env change.
 *
 * Report-centric: the dashboard works with reports, not cases.
 */
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

export type ReportStatus = 'draft' | 'confirmed' | 'superseded' | 'withdrawn' | 'abandoned';

export interface ProductApiClient {
  // Auth
  signup(body: SignupRequest): Promise<TokenResponse>;
  login(body: LoginRequest): Promise<TokenResponse>;
  getMe(): Promise<MeResponse>;

  // Org profile & onboarding
  getOrgProfile(): Promise<OrgProfile>;
  putOrgProfile(body: OrgProfile): Promise<OrgProfile>;
  getCollectionTemplates(): Promise<CollectionTemplate[]>;
  getRecommendedCollection(): Promise<RecommendedTemplates>;
  getDashboardTemplates(): Promise<DashboardTemplate[]>;
  putBotConfig(body: BotConfig): Promise<BotConfig>;
  putDashboardConfig(body: DashboardConfig): Promise<DashboardConfig>;

  // Data protection
  getDataProtection(): Promise<DataProtectionConfig>;
  putDataProtection(body: DataProtectionConfig): Promise<DataProtectionConfig>;

  // Channels
  getChannels(): Promise<ChannelsConfig>;
  putChannels(body: ChannelsConfig): Promise<ChannelsConfig>;

  // Contacts
  importContacts(file: File): Promise<ContactImportResult>;
  getContacts(): Promise<Contact[]>;

  // Dashboard
  getDashboardSummary(): Promise<DashboardSummary>;
  getDashboardAreas(): Promise<AreaCount[]>;
  getFeed(since?: string): Promise<FeedResponse>;

  // Reports
  getReports(status?: ReportStatus): Promise<ReportSummary[]>;
  getReport(id: string): Promise<ReportDetail>;
  patchReport(id: string, body: ReportPatch): Promise<ReportDetail>;

  // Campaigns
  getCampaigns(): Promise<Campaign[]>;
  createCampaign(body: CampaignCreate): Promise<Campaign>;
  suggestCampaignFields(body: SuggestFieldsRequest): Promise<SuggestFieldsResponse>;

  // Ask
  ask(body: AskRequest): Promise<AskResponse>;
}

/** Error envelope from the Dashboard API: `{"error": {code, message, details}}`. */
export interface ApiErrorBody {
  code: string;
  message: string;
  details?: unknown;
}

export class ProductApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: unknown;

  constructor(body: ApiErrorBody, status: number) {
    super(body.message || body.code);
    this.name = 'ProductApiError';
    this.code = body.code;
    this.status = status;
    this.details = body.details ?? null;
  }
}
