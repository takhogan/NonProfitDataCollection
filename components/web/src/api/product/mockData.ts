/**
 * Synthetic data for `MockProductClient`, mirroring the Dashboard API
 * CONTRACT.md examples (Miami Mutual Aid, Miami-Dade neighborhoods). Values are
 * illustrative; shapes match the contract exactly.
 */
import type {
  AreaCount,
  Campaign,
  ChannelsConfig,
  CollectionTemplate,
  Contact,
  DashboardTemplate,
  FeedItem,
  MeResponse,
  OrgProfile,
  RecommendedTemplates,
  ReportDetail,
} from '../generated';

export const DEMO_EMAIL = 'demo@metron.org';
export const DEMO_PASSWORD = 'demo-pass';

export const ME: MeResponse = {
  id: 'user-demo',
  email: DEMO_EMAIL,
  display_name: 'Demo Admin',
  memberships: [{ organization_id: 'org-demo', organization_name: 'Miami Mutual Aid', role: 'org_admin' }],
};

export const ORG_PROFILE: OrgProfile = {
  name: 'Miami Mutual Aid',
  type: 'community',
  mission: 'Coordinate power and water relief across Miami-Dade neighborhoods.',
  region: 'Miami-Dade, FL',
  languages: ['en', 'es', 'ht'],
  population_served: 'Low-income and elderly residents in flood-prone areas',
  team_size: 12,
};

export const COLLECTION_TEMPLATES: CollectionTemplate[] = [
  {
    id: 'power_water_outages',
    name: 'Power & Water Outages',
    description: 'Track electricity and piped-water status and needs.',
    questions: [
      { key: 'power_status', label: '¿Cómo está la electricidad?', field_type: 'choice', options: ['available', 'unavailable', 'intermittent', 'unknown'] },
      { key: 'water_status', label: '¿Cómo está el agua?', field_type: 'choice', options: ['available', 'unavailable', 'intermittent', 'unknown'] },
      { key: 'household_size', label: '¿Cuántas personas hay en casa?', field_type: 'number', options: null },
      { key: 'urgent_needs', label: '¿Hay una necesidad urgente?', field_type: 'text', options: null },
    ],
    fields: ['power_status', 'water_status', 'household_size', 'urgent_needs', 'area'],
  },
  {
    id: 'food_security',
    name: 'Food Security',
    description: 'Check how many days of food a household has and what it needs.',
    questions: [
      { key: 'days_of_food', label: '¿Para cuántos días tiene comida?', field_type: 'number', options: null },
      { key: 'household_size', label: '¿Cuántas personas hay en casa?', field_type: 'number', options: null },
      { key: 'dietary_needs', label: '¿Necesidades alimentarias especiales?', field_type: 'text', options: null },
    ],
    fields: ['days_of_food', 'household_size', 'dietary_needs', 'area'],
  },
  {
    id: 'elderly_check_ins',
    name: 'Elderly Check-ins',
    description: 'Wellbeing check-ins for elderly or isolated residents.',
    questions: [
      { key: 'is_ok', label: '¿Se encuentra bien hoy?', field_type: 'boolean', options: null },
      { key: 'needs_medication', label: '¿Necesita medicamentos?', field_type: 'boolean', options: null },
      { key: 'needs_help', label: '¿En qué podemos ayudarle?', field_type: 'text', options: null },
    ],
    fields: ['is_ok', 'needs_medication', 'needs_help', 'area'],
  },
  {
    id: 'disaster_needs',
    name: 'Disaster Needs',
    description: 'Rapid needs assessment after a storm or flood.',
    questions: [
      { key: 'shelter_status', label: '¿Tiene un lugar seguro?', field_type: 'choice', options: ['safe', 'displaced', 'at_risk', 'unknown'] },
      { key: 'top_need', label: '¿Cuál es su necesidad más urgente?', field_type: 'text', options: null },
      { key: 'household_size', label: '¿Cuántas personas hay en casa?', field_type: 'number', options: null },
    ],
    fields: ['shelter_status', 'top_need', 'household_size', 'area'],
  },
  {
    id: 'beneficiary_feedback',
    name: 'Beneficiary Feedback',
    description: 'Hear how the people you serve rate the help they received.',
    questions: [
      { key: 'received_help', label: '¿Recibió la ayuda?', field_type: 'boolean', options: null },
      { key: 'satisfaction', label: '¿Qué tan satisfecho está? (1-5)', field_type: 'number', options: null },
      { key: 'comments', label: '¿Algún comentario?', field_type: 'text', options: null },
    ],
    fields: ['received_help', 'satisfaction', 'comments', 'area'],
  },
  {
    id: 'aid_confirmation',
    name: 'Grant / Aid Confirmation',
    description: 'Confirm that aid actually reached the intended recipient.',
    questions: [
      { key: 'aid_received', label: '¿Confirmó la ayuda?', field_type: 'boolean', options: null },
      { key: 'aid_type', label: '¿Qué tipo de ayuda?', field_type: 'text', options: null },
      { key: 'received_at', label: '¿Cuándo la recibió?', field_type: 'text', options: null },
    ],
    fields: ['aid_received', 'aid_type', 'received_at', 'area'],
  },
];

export const RECOMMENDED_COLLECTION: RecommendedTemplates = {
  recommended_collection_ids: ['power_water_outages', 'elderly_check_ins'],
  reason: 'Based on your region and population served (outage-prone, elderly residents).',
};

export const DASHBOARD_TEMPLATES: DashboardTemplate[] = [
  {
    id: 'needs_overview',
    name: 'Needs Overview',
    description: 'Summary metrics, area breakdown, and a live feed.',
    widgets: [
      { key: 'summary', label: 'AI Summary', type: 'metric' },
      { key: 'metrics', label: 'Key Metrics', type: 'metric' },
      { key: 'areas', label: 'By Neighborhood', type: 'list' },
      { key: 'feed', label: 'Live Feed', type: 'feed' },
    ],
    recommended: true,
  },
  {
    id: 'map_first',
    name: 'Map-first',
    description: 'A map of need, with metrics and a feed alongside.',
    widgets: [
      { key: 'map', label: 'Need Map', type: 'map' },
      { key: 'metrics', label: 'Key Metrics', type: 'metric' },
      { key: 'feed', label: 'Live Feed', type: 'feed' },
    ],
    recommended: false,
  },
  {
    id: 'case_management',
    name: 'Case Management',
    description: 'Reports table and urgent queue for triage teams.',
    widgets: [
      { key: 'summary', label: 'AI Summary', type: 'metric' },
      { key: 'reports', label: 'Reports', type: 'list' },
      { key: 'urgent', label: 'Urgent Queue', type: 'list' },
      { key: 'trend', label: 'Trend', type: 'chart' },
    ],
    recommended: false,
  },
];

export const CHANNELS: ChannelsConfig = {
  channels: [
    { channel: 'whatsapp', status: 'connected', identifier: '+1 305 555 0142', mode: 'shared_bot' },
    { channel: 'sms', status: 'disconnected', identifier: null, mode: 'own_number' },
    { channel: 'telegram', status: 'disconnected', identifier: null, mode: 'own_number' },
    { channel: 'email', status: 'disconnected', identifier: null, mode: 'own_number' },
  ],
};

/** Raw (unmasked) contacts; the mock applies privacy filtering before returning. */
export const CONTACTS_RAW: Contact[] = [
  { id: 'c1', name: 'Marie Pierre', phone: '+13055550142', area: 'Little Haiti', consent_status: 'granted', last_contact_at: null },
  { id: 'c2', name: 'José Díaz', phone: '+13055550199', area: 'Hialeah', consent_status: 'pending', last_contact_at: null },
  { id: 'c3', name: 'Alice Johnson', phone: '+13055550177', area: 'Liberty City', consent_status: 'granted', last_contact_at: null },
  { id: 'c4', name: 'Fredline Joseph', phone: '+13055550121', area: 'Little Haiti', consent_status: 'declined', last_contact_at: null },
];

export const AREAS: AreaCount[] = [
  { area: 'Little Haiti', reports: 18, without_power: 12, without_water: 4, urgent: 5 },
  { area: 'Liberty City', reports: 14, without_power: 6, without_water: 9, urgent: 3 },
  { area: 'Allapattah', reports: 11, without_power: 7, without_water: 2, urgent: 4 },
  { area: 'Overtown', reports: 8, without_power: 3, without_water: 3, urgent: 1 },
  { area: 'Hialeah', reports: 6, without_power: 2, without_water: 1, urgent: 0 },
];

/** Feed items, newest last. `received_at` strictly increasing for cursor polling. */
export const FEED_SEED: FeedItem[] = [
  { id: 'msg-1', received_at: '2026-11-08T13:40:00+00:00', area: 'Little Haiti', channel: 'whatsapp', preview: 'Sin luz desde anoche, 3 personas mayores en casa.', tags: ['no_power', 'elderly', 'urgent'], report_id: 'report-1' },
  { id: 'msg-2', received_at: '2026-11-08T13:45:00+00:00', area: 'Liberty City', channel: 'whatsapp', preview: 'No hay agua en el edificio desde ayer.', tags: ['no_water'], report_id: 'report-2' },
  { id: 'msg-3', received_at: '2026-11-08T13:51:00+00:00', area: 'Allapattah', channel: 'sms', preview: 'Necesito cargar el oxígeno de mi mamá, no hay corriente.', tags: ['no_power', 'medical', 'urgent'], report_id: 'report-3' },
  { id: 'msg-4', received_at: '2026-11-08T13:56:00+00:00', area: 'Overtown', channel: 'whatsapp', preview: 'Ya volvió la luz en mi cuadra, gracias.', tags: ['power_restored'], report_id: null },
];

/** Later items the mock "receives" over time, to animate the live feed. */
export const FEED_INCOMING: FeedItem[] = [
  { id: 'msg-5', received_at: '2026-11-08T14:02:00+00:00', area: 'Little Haiti', channel: 'whatsapp', preview: 'Somos 5 en casa y no tenemos agua potable.', tags: ['no_water', 'urgent'], report_id: 'report-5' },
  { id: 'msg-6', received_at: '2026-11-08T14:08:00+00:00', area: 'Hialeah', channel: 'telegram', preview: 'La electricidad va y viene todo el día.', tags: ['intermittent_power'], report_id: 'report-6' },
  { id: 'msg-7', received_at: '2026-11-08T14:15:00+00:00', area: 'Liberty City', channel: 'whatsapp', preview: 'Mi vecina mayor necesita medicamentos, no puede salir.', tags: ['elderly', 'medical', 'urgent'], report_id: 'report-7' },
];

export function reportsSeed(): ReportDetail[] {
  return [
    {
      id: 'report-1', area: 'Little Haiti', status: 'confirmed', urgent: true,
      submitted_at: '2026-11-08T13:00:00+00:00', source_channel: 'whatsapp',
      service_type: 'electricity', service_status: 'unavailable',
      tags: ['no_power', 'elderly'], reporter_name: 'Marie Pierre', reporter_phone: '+13055550142',
      assignee: null, notes: '',
      transcript: [
        { from: 'reporter', at: '2026-11-08T13:00:00+00:00', text: 'Hola, no tengo luz desde anoche.' },
        { from: 'bot', at: '2026-11-08T13:00:00+00:00', text: 'Gracias. ¿Cuántas personas hay en casa?' },
        { from: 'reporter', at: '2026-11-08T13:00:00+00:00', text: 'Somos 3, dos son mayores.' },
      ],
      extracted_fields: { power_status: 'unavailable', water_status: 'unknown', household_size: 3, urgent_needs: ['no_power', 'elderly'], days_without_water: null },
    },
    {
      id: 'report-2', area: 'Liberty City', status: 'confirmed', urgent: false,
      submitted_at: '2026-11-08T12:30:00+00:00', source_channel: 'whatsapp',
      service_type: 'piped_water', service_status: 'unavailable',
      tags: ['no_water'], reporter_name: 'Alice Johnson', reporter_phone: '+13055550177',
      assignee: null, notes: '',
      transcript: [
        { from: 'reporter', at: '2026-11-08T12:30:00+00:00', text: 'No hay agua en el edificio desde ayer.' },
        { from: 'bot', at: '2026-11-08T12:30:00+00:00', text: '¿Cuántos días lleva sin agua?' },
        { from: 'reporter', at: '2026-11-08T12:31:00+00:00', text: 'Un día.' },
      ],
      extracted_fields: { power_status: 'available', water_status: 'unavailable', household_size: 4, urgent_needs: ['no_water'], days_without_water: 1 },
    },
    {
      id: 'report-3', area: 'Allapattah', status: 'review', urgent: true,
      submitted_at: '2026-11-08T11:50:00+00:00', source_channel: 'sms',
      service_type: 'electricity', service_status: 'unavailable',
      tags: ['no_power', 'medical'], reporter_name: 'José Díaz', reporter_phone: '+13055550199',
      assignee: null, notes: 'Oxygen concentrator — follow up fast.',
      transcript: [
        { from: 'reporter', at: '2026-11-08T11:50:00+00:00', text: 'Necesito cargar el oxígeno de mi mamá, no hay corriente.' },
        { from: 'bot', at: '2026-11-08T11:50:00+00:00', text: 'Entiendo, es urgente. ¿Dónde se encuentran?' },
        { from: 'reporter', at: '2026-11-08T11:51:00+00:00', text: 'En Allapattah, cerca del mercado.' },
      ],
      extracted_fields: { power_status: 'unavailable', water_status: 'available', household_size: 2, urgent_needs: ['no_power', 'medical'], days_without_water: null },
    },
    {
      id: 'report-4', area: 'Overtown', status: 'draft', urgent: false,
      submitted_at: '2026-11-08T10:15:00+00:00', source_channel: 'whatsapp',
      service_type: 'electricity', service_status: 'intermittent',
      tags: ['intermittent_power'], reporter_name: 'Fredline Joseph', reporter_phone: '+13055550121',
      assignee: null, notes: '',
      transcript: [
        { from: 'reporter', at: '2026-11-08T10:15:00+00:00', text: 'La luz va y viene.' },
      ],
      extracted_fields: { power_status: 'intermittent', water_status: 'available', household_size: 1, urgent_needs: [], days_without_water: null },
    },
  ];
}

export function campaignsSeed(): Campaign[] {
  return [
    {
      id: 'camp-1', name: 'November Outage Watch', collection_template_id: 'power_water_outages',
      areas: ['Little Haiti', 'Liberty City', 'Overtown', 'Allapattah'], status: 'active',
      starts_at: '2026-11-01T00:00:00+00:00', ends_at: null,
    },
  ];
}
