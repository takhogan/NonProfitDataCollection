import { describe, expect, it } from 'vitest';
import { homeFor, navFor } from './nav';

describe('role-aware navigation (WEB-001/002)', () => {
  it('lands each role on its home view', () => {
    expect(homeFor(['provider'])).toBe('/areas');
    expect(homeFor(['coordinator'])).toBe('/data-health');
    expect(homeFor(['reviewer'])).toBe('/review');
    expect(homeFor(['intake_volunteer'])).toBe('/intake/new');
    expect(homeFor(['analyst'])).toBe('/indicators');
    expect(homeFor(['org_admin'])).toBe('/admin');
  });

  it('shows only what the role allows', () => {
    const reviewer = navFor(['reviewer']).map((i) => i.path);
    expect(reviewer).toEqual(['/review']);
    const coordinator = navFor(['coordinator']).map((i) => i.path);
    expect(coordinator).not.toContain('/activities');
    expect(coordinator).toContain('/coverage');
  });
});
