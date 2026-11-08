import { describe, expect, it } from 'vitest';
import { MockApiClient } from './mockClient';
import { TENANT } from './data';

const now = Date.parse('2026-11-07T16:00:00Z');
const client = () => new MockApiClient({ now, latencyMs: 0 });

describe('mock API: indicator cells', () => {
  it('suppresses cells under k and never reports unknown as zero (DOM-041/044)', async () => {
    const cells = await client().getIndicators({ level: 'sector', bucket: '24h', category: 'water_drinking' });
    for (const c of cells) {
      if (c.coverage_label === 'none' || c.suppressed) {
        expect(c.active_needs).toBeNull();
        expect(c.distinct_reporters).toBeNull();
      } else {
        expect(c.distinct_reporters!).toBeGreaterThanOrEqual(TENANT.k);
      }
      expect(c.active_needs).not.toBe(0);
    }
    expect(cells.some((c) => c.suppressed)).toBe(true);
    expect(cells.some((c) => c.coverage_label === 'none')).toBe(true);
  });

  it('every cell has a confidence label with reasons and a method version', async () => {
    const cells = await client().getIndicators({ level: 'parish', bucket: '7d' });
    for (const c of cells) {
      expect(['low', 'medium', 'high']).toContain(c.confidence.level);
      expect(c.confidence.reasons.length).toBeGreaterThan(0);
      expect(c.method_version).toBeTruthy();
    }
  });
});

describe('mock API: ranking (DOM-043)', () => {
  it('orders by urgent needs, then needs per reporter', async () => {
    const r = await client().getAreasOfNeed({ level: 'sector', bucket: '24h' });
    expect(r.criteria.map((c) => c.key)).toEqual([
      'urgent_active_needs',
      'needs_per_reporter',
      'oldest_unmet_need',
      'freshness',
    ]);
    for (let i = 1; i < r.items.length; i++) {
      const a = r.items[i - 1]!.criteria_values;
      const b = r.items[i]!.criteria_values;
      expect(a.urgent_active_needs).toBeGreaterThanOrEqual(b.urgent_active_needs);
      if (a.urgent_active_needs === b.urgent_active_needs) {
        expect(a.needs_per_reporter).toBeGreaterThanOrEqual(b.needs_per_reporter);
      }
    }
    expect(r.unranked.every((c) => c.suppressed || c.coverage_label === 'none')).toBe(true);
  });
});

describe('mock API: activities and coverage', () => {
  it('a logged active activity covers its cells immediately (WEB-014, DOM-052)', async () => {
    const api = client();
    const before = await api.getCoverage({ bucket: '24h', category: 'water_drinking' });
    const gap = before.items.find((c) => c.status === 'uncovered' && c.high_need)!;
    expect(gap).toBeDefined();
    await api.createActivity({
      operation_key: 'k1',
      type: 'water_distribution_point',
      category: 'water_drinking',
      area_ids: [gap.area.id],
      schedule: { kind: 'recurring', days: ['mon'], start_time: '08:00', end_time: '10:00' },
      capacity: null,
      public_location_id: null,
      visibility: 'all_providers',
      status: 'active',
    });
    const after = await api.getCoverage({ bucket: '24h', category: 'water_drinking' });
    expect(after.items.find((c) => c.area.id === gap.area.id)!.status).toBe('covered');
  });

  it('is idempotent per operation key', async () => {
    const api = client();
    const cmd = {
      operation_key: 'same',
      type: 'charging_point' as const,
      category: 'charging' as const,
      area_ids: ['sec-brisas'],
      schedule: { kind: 'recurring' as const, days: ['sat' as const], start_time: '08:00', end_time: '10:00' },
      capacity: null,
      public_location_id: null,
      visibility: 'all_providers' as const,
      status: 'active' as const,
    };
    const a = await api.createActivity(cmd);
    const b = await api.createActivity(cmd);
    expect(b.id).toBe(a.id);
    expect((await api.listActivities({ mine: true })).filter((x) => x.id === a.id)).toHaveLength(1);
  });

  it('hides details of other providers\' internal-only activities (DOM-053)', async () => {
    const acts = await client().listActivities();
    const internal = acts.find((a) => a.id === 'act-5')!;
    expect(internal.details_hidden).toBe(true);
    expect(internal.schedule).toBeNull();
  });

  it('flags activities unconfirmed for 7 days (DOM-051)', async () => {
    const acts = await client().listActivities({ mine: true });
    expect(acts.find((a) => a.id === 'act-2')!.unconfirmed).toBe(true);
    expect(acts.find((a) => a.id === 'act-1')!.unconfirmed).toBe(false);
  });

  it('rejects stale versions', async () => {
    const api = client();
    await expect(api.updateActivity('act-1', { operation_key: 'x', version: 99, status: 'paused' })).rejects.toMatchObject({
      code: 'stale_version',
    });
  });
});
