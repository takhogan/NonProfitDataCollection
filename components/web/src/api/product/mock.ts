import type {
  AreaCount,
  AskRequest,
  AskResponse,
  BotConfig,
  Campaign,
  CampaignCreate,
  CampaignField,
  ChannelsConfig,
  CollectionTemplate,
  Contact,
  ContactImportResult,
  DashboardConfig,
  DashboardSummary,
  DashboardTemplate,
  DataProtectionConfig,
  FeedItem,
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
import type { ProductApiClient, ReportStatus } from './client';
import { ProductApiError } from './client';
import { setToken } from './token';
import {
  AREAS,
  campaignsSeed,
  CHANNELS,
  COLLECTION_TEMPLATES,
  CONTACTS_RAW,
  DASHBOARD_TEMPLATES,
  DEMO_EMAIL,
  DEMO_PASSWORD,
  FEED_INCOMING,
  FEED_SEED,
  ME,
  ORG_PROFILE,
  RECOMMENDED_COLLECTION,
  reportsSeed,
} from './mockData';

function clone<T>(x: T): T {
  return structuredClone(x);
}

/**
 * Persist mutable mock state across page reloads so the demo stays consistent
 * (e.g. toggling data protection in Settings is still in effect after a reload).
 * Only mock state — never real data. Falls back to in-memory if storage fails.
 */
const STORE_KEY = 'metron.mock.state';
function loadState<T>(fallback: T): T {
  try {
    const raw = sessionStorage.getItem(STORE_KEY);
    if (raw) return { ...fallback, ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return fallback;
}
function saveState(state: unknown) {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify(state));
  } catch {
    /* ignore */
  }
}

/** Clear persisted mock state (called on sign-out so a fresh demo resets). */
export function resetMockState() {
  try {
    sessionStorage.removeItem(STORE_KEY);
  } catch {
    /* ignore */
  }
}

/** Mask a phone like the API does: keep the last 2 digits, e.g. `•••••42`. */
function maskPhone(phone: string | null | undefined): string | null {
  if (!phone) return phone ?? null;
  const digits = phone.replace(/\D/g, '');
  const tail = digits.slice(-2);
  return `•••••${tail}`;
}

/**
 * In-memory implementation of the Dashboard API contract. Applies the same
 * privacy filtering the real API applies server-side, so the UI behaves
 * identically against mock and live backends.
 */
interface PersistedState {
  orgProfile: OrgProfile;
  channels: ChannelsConfig;
  botConfig: BotConfig;
  dashboardConfig: DashboardConfig;
  dataProtection: DataProtectionConfig;
  campaigns: Campaign[];
}

export class MockProductClient implements ProductApiClient {
  private readonly startedAt = Date.now();
  private reports: ReportDetail[] = reportsSeed();
  private state: PersistedState;
  private readonly latencyMs: number;

  constructor(opts: { latencyMs?: number } = {}) {
    this.latencyMs = opts.latencyMs ?? 220;
    this.state = loadState<PersistedState>({
      orgProfile: clone(ORG_PROFILE),
      channels: clone(CHANNELS),
      botConfig: { greeting: '', language_default: 'es', collection_template_id: 'power_water_outages', ask_consent: true, human_handoff_enabled: true },
      dashboardConfig: { template_id: 'needs_overview', widgets: ['summary', 'metrics', 'areas', 'feed'] },
      dataProtection: {
        preset: 'standard', store_names: true, location_precision: 'precise', raw_message_retention_days: 90,
        mask_phone_numbers: false, redact_exports: false, individual_records_roles: ['org_admin', 'coordinator'], audit_log_enabled: true,
        hide_individual_records: false,
      },
      campaigns: campaignsSeed(),
    });
  }

  private persist() {
    saveState(this.state);
  }
  private get orgProfile() { return this.state.orgProfile; }
  private set orgProfile(v: OrgProfile) { this.state.orgProfile = v; this.persist(); }
  private get channels() { return this.state.channels; }
  private set channels(v: ChannelsConfig) { this.state.channels = v; this.persist(); }
  private get botConfig() { return this.state.botConfig; }
  private set botConfig(v: BotConfig) { this.state.botConfig = v; this.persist(); }
  private get dashboardConfig() { return this.state.dashboardConfig; }
  private set dashboardConfig(v: DashboardConfig) { this.state.dashboardConfig = v; this.persist(); }
  private get dataProtection() { return this.state.dataProtection; }
  private set dataProtection(v: DataProtectionConfig) { this.state.dataProtection = v; this.persist(); }
  private get campaigns() { return this.state.campaigns; }
  private set campaigns(v: Campaign[]) { this.state.campaigns = v; this.persist(); }

  private async delay() {
    if (this.latencyMs <= 0) return;
    await new Promise((r) => setTimeout(r, this.latencyMs * (0.6 + Math.random() * 0.8)));
  }
  private async ok<T>(v: T): Promise<T> {
    await this.delay();
    return clone(v);
  }

  /** Apply the org's data-protection settings to anything carrying personal fields. */
  private filterReporter<T extends { reporter_name?: string | null; reporter_phone?: string | null }>(r: T): T {
    const out = { ...r };
    if (!this.dataProtection.store_names) out.reporter_name = null;
    if (this.dataProtection.mask_phone_numbers) out.reporter_phone = maskPhone(out.reporter_phone);
    return out;
  }

  // ---- Auth ----
  async signup(b: SignupRequest): Promise<TokenResponse> {
    await this.delay();
    if (!b.email || !b.password || !b.org_name) {
      throw new ProductApiError({ code: 'validation_error', message: 'Email, password and organization name are required.' }, 422);
    }
    this.orgProfile = { ...this.orgProfile, name: b.org_name, type: b.org_type ?? 'community' };
    const token = `mock.${btoa(b.email).replace(/=/g, '')}.signup`;
    setToken(token);
    return { access_token: token, token_type: 'bearer' };
  }
  async login(b: LoginRequest): Promise<TokenResponse> {
    await this.delay();
    if (b.email !== DEMO_EMAIL || b.password !== DEMO_PASSWORD) {
      throw new ProductApiError({ code: 'permission_denied', message: 'Invalid email or password.' }, 403);
    }
    const token = `mock.${btoa(b.email).replace(/=/g, '')}.login`;
    setToken(token);
    return { access_token: token, token_type: 'bearer' };
  }
  getMe(): Promise<MeResponse> {
    const memberships = ME.memberships.map((m) => ({ ...m, organization_name: this.orgProfile.name }));
    return this.ok({ ...ME, memberships });
  }

  // ---- Org profile & onboarding ----
  getOrgProfile() {
    return this.ok(this.orgProfile);
  }
  putOrgProfile(b: OrgProfile) {
    this.orgProfile = clone(b);
    return this.ok(this.orgProfile);
  }
  getCollectionTemplates(): Promise<CollectionTemplate[]> {
    return this.ok(COLLECTION_TEMPLATES);
  }
  getRecommendedCollection(): Promise<RecommendedTemplates> {
    return this.ok(RECOMMENDED_COLLECTION);
  }
  getDashboardTemplates(): Promise<DashboardTemplate[]> {
    return this.ok(DASHBOARD_TEMPLATES);
  }
  putBotConfig(b: BotConfig) {
    this.botConfig = clone(b);
    return this.ok(this.botConfig);
  }
  putDashboardConfig(b: DashboardConfig) {
    this.dashboardConfig = clone(b);
    return this.ok(this.dashboardConfig);
  }

  // ---- Data protection ----
  getDataProtection() {
    return this.ok(this.dataProtection);
  }
  putDataProtection(b: DataProtectionConfig) {
    this.dataProtection = clone(b);
    return this.ok(this.dataProtection);
  }

  // ---- Channels ----
  getChannels() {
    return this.ok(this.channels);
  }
  putChannels(b: ChannelsConfig) {
    this.channels = clone(b);
    return this.ok(this.channels);
  }

  // ---- Contacts ----
  async importContacts(file: File): Promise<ContactImportResult> {
    await this.delay();
    // Count non-empty, non-header lines as imported rows.
    const text = await file.text().catch(() => '');
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const rows = Math.max(0, lines.length - 1);
    return { imported: rows || CONTACTS_RAW.length, skipped: 0, errors: [] };
  }
  getContacts(): Promise<Contact[]> {
    const filtered = CONTACTS_RAW.map((c) => ({
      ...c,
      name: this.dataProtection.store_names ? c.name : null,
      phone: this.dataProtection.mask_phone_numbers ? maskPhone(c.phone) : c.phone,
    }));
    return this.ok(filtered);
  }

  // ---- Dashboard ----
  getDashboardSummary(): Promise<DashboardSummary> {
    const live = this.liveFeed();
    const reportsToday = this.reports.length;
    const withoutPower = this.reports.filter((r) => r.service_type === 'electricity' && r.service_status === 'unavailable').length;
    const withoutWater = this.reports.filter((r) => r.service_type === 'piped_water' && r.service_status === 'unavailable').length;
    const urgent = this.reports.filter((r) => r.urgent).length;
    void live;
    return this.ok({
      summary: `${reportsToday} reports today across ${this.orgProfile.name}: ${withoutPower} without power, ${withoutWater} without water, ${urgent} urgent. Little Haiti and Allapattah are the hardest hit.`,
      metrics: { reports_today: reportsToday, without_power: withoutPower, without_water: withoutWater, urgent },
      generated_at: new Date().toISOString(),
    });
  }
  getDashboardAreas(): Promise<AreaCount[]> {
    return this.ok(AREAS);
  }
  getFeed(since?: string): Promise<FeedResponse> {
    const all = this.liveFeed();
    const items = since ? all.filter((i) => i.received_at > since) : all;
    const cursor = (items.length ? items : all).at(-1)?.received_at ?? since ?? new Date(0).toISOString();
    return this.ok({ items, cursor });
  }
  /** Feed grows over time so polling shows new messages sliding in. */
  private liveFeed(): FeedItem[] {
    const elapsedSec = (Date.now() - this.startedAt) / 1000;
    const extra = Math.min(FEED_INCOMING.length, Math.floor(elapsedSec / 12));
    return [...FEED_SEED, ...FEED_INCOMING.slice(0, extra)];
  }

  // ---- Reports ----
  getReports(status?: ReportStatus): Promise<ReportSummary[]> {
    const list = this.reports
      .filter((r) => !status || r.status === status)
      .map((r) => this.toSummary(r));
    return this.ok(list);
  }
  getReport(id: string): Promise<ReportDetail> {
    const r = this.reports.find((x) => x.id === id);
    if (!r) throw new ProductApiError({ code: 'not_found', message: 'Report not found.' }, 404);
    return this.ok(this.filterReporter(r));
  }
  async patchReport(id: string, b: ReportPatch): Promise<ReportDetail> {
    await this.delay();
    const r = this.reports.find((x) => x.id === id);
    if (!r) throw new ProductApiError({ code: 'not_found', message: 'Report not found.' }, 404);
    if (b.status != null) r.status = b.status;
    if (b.notes != null) r.notes = b.notes;
    if (b.assignee !== undefined) r.assignee = b.assignee;
    return clone(this.filterReporter(r));
  }
  private toSummary(r: ReportDetail): ReportSummary {
    const f = this.filterReporter(r);
    return {
      id: f.id, area: f.area, status: f.status, urgent: f.urgent, submitted_at: f.submitted_at,
      source_channel: f.source_channel, service_type: f.service_type, service_status: f.service_status,
      tags: f.tags, reporter_name: f.reporter_name, reporter_phone: f.reporter_phone, assignee: f.assignee,
    };
  }

  // ---- Campaigns ----
  getCampaigns(): Promise<Campaign[]> {
    return this.ok(this.campaigns);
  }
  async createCampaign(b: CampaignCreate): Promise<Campaign> {
    await this.delay();
    if (!b.name) throw new ProductApiError({ code: 'validation_error', message: 'Campaign name is required.' }, 422);
    const camp: Campaign = {
      id: `camp-${this.campaigns.length + 1}`, name: b.name, collection_template_id: b.collection_template_id,
      areas: b.areas ?? [], status: 'active', starts_at: b.starts_at ?? new Date().toISOString(), ends_at: b.ends_at ?? null,
      fields: b.fields ?? [],
    };
    this.campaigns = [camp, ...this.campaigns];
    return clone(camp);
  }
  async suggestCampaignFields(b: SuggestFieldsRequest): Promise<SuggestFieldsResponse> {
    await this.delay();
    const tpl = COLLECTION_TEMPLATES.find((t) => t.id === b.collection_template_id) ?? COLLECTION_TEMPLATES[0];
    const fields = tpl ? fieldsFromTemplate(tpl) : [];
    return { fields, source: 'fallback', model: null };
  }

  // ---- Ask ----
  async ask(b: AskRequest): Promise<AskResponse> {
    await this.delay();
    const top = [...AREAS].sort((a, z) => z.urgent - a.urgent)[0] ?? { area: 'Little Haiti', urgent: 0 };
    return {
      answer: `In the last 24 hours, ${top.area} had the most urgent reports (${top.urgent}), mostly elderly residents without power. Allapattah follows with medical-device charging needs.`,
      data: { top_area: top.area, urgent_count: top.urgent, question: b.question },
    };
  }
}

/** Synthesize CampaignFields from a collection template's questions (mock fallback
 * for POST /campaigns/suggest-fields). Area is always present and first. */
function fieldsFromTemplate(tpl: CollectionTemplate): CampaignField[] {
  const area: CampaignField = {
    id: 'area', label_es: 'Zona / barrio', label_en: 'Area / neighborhood',
    question_es: '¿En qué zona o barrio se encuentra?', question_en: 'Which area or neighborhood are you in?',
    kind: 'core', core_key: 'area', options: null, unit: null, required: true,
    rationale: 'Every report is mapped by area.', recommended: true,
  };
  const KIND: Record<string, CampaignField['kind']> = {
    boolean: 'boolean', number: 'number', choice: 'choice', text: 'text', location: 'core',
  };
  const custom: CampaignField[] = (tpl.questions ?? []).map((q, i) => {
    const kind = KIND[q.field_type] ?? 'text';
    return {
      id: q.key,
      label_es: q.label, label_en: q.label,
      question_es: q.label, question_en: q.label,
      kind,
      core_key: null,
      options: kind === 'choice' && q.options
        ? q.options.map((o) => ({ value: o, label_es: o, label_en: o }))
        : null,
      unit: kind === 'number' ? '' : null,
      required: false,
      rationale: 'Suggested from your selected template.',
      recommended: i < 3,
    };
  });
  return [area, ...custom].slice(0, 8);
}
