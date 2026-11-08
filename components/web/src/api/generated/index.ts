/**
 * Friendly aliases over the auto-generated OpenAPI schema
 * (`schema.gen.ts`, produced by `npm run gen:api` from
 * `../../../../api/openapi.json`). Feature code imports these names, never the
 * raw `components['schemas'][...]` form.
 *
 * Regenerate after a contract change:
 *     npm run gen:api
 * and keep this alias list in sync with the Dashboard API CONTRACT.md.
 */
import type { components } from './schema.gen';

type S = components['schemas'];

// Auth / identity
export type TokenResponse = S['TokenResponse'];
export type LoginRequest = S['LoginRequest'];
export type SignupRequest = S['SignupRequest'];
export type MeResponse = S['MeResponse'];
export type Membership = S['MembershipOut'];

// Org profile & onboarding
export type OrgProfile = S['OrgProfile'];
export type CollectionTemplate = S['CollectionTemplate'];
export type TemplateQuestion = S['TemplateQuestion'];
export type RecommendedTemplates = S['RecommendedTemplates'];
export type DashboardTemplate = S['DashboardTemplate'];
export type DashboardWidget = S['DashboardWidget'];
export type BotConfig = S['BotConfig'];
export type DashboardConfig = S['DashboardConfig'];

// Data protection
export type DataProtectionConfig = S['DataProtectionConfig'];

// Channels
export type ChannelsConfig = S['ChannelsConfig'];
export type Channel = S['Channel'];

// Contacts
export type Contact = S['Contact'];
export type ContactImportResult = S['ContactImportResult'];

// Dashboard
export type DashboardSummary = S['DashboardSummary'];
export type DashboardMetrics = S['DashboardMetrics'];
export type AreaCount = S['AreaCount'];
export type FeedResponse = S['FeedResponse'];
export type FeedItem = S['FeedItem'];

// Reports (report-centric; replaces cases)
export type ReportSummary = S['ReportSummary'];
export type ReportDetail = S['ReportDetail'];
export type ReportPatch = S['ReportPatch'];
export type TranscriptLine = S['TranscriptLine'];

// Campaigns
export type Campaign = S['Campaign'];
export type CampaignCreate = S['CampaignCreate'];
export type CampaignField = S['CampaignField'];
export type CampaignFieldOption = S['CampaignFieldOption'];
export type SuggestFieldsRequest = S['SuggestFieldsRequest'];
export type SuggestFieldsResponse = S['SuggestFieldsResponse'];
export type CampaignResults = S['CampaignResults'];
export type FieldAggregate = S['FieldAggregate'];

// Ask
export type AskRequest = S['AskRequest'];
export type AskResponse = S['AskResponse'];
