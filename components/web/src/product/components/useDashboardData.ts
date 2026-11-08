import { useMemo } from 'react';
import { useReports } from '../../api/product/queries';
import type { ReportSummary } from '../../api/product';

export type TimeRange = 'today' | '7d' | 'all';

const DAY = 24 * 3600_000;

function withinRange(iso: string, range: TimeRange, now: number): boolean {
  if (range === 'all') return true;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return true;
  if (range === 'today') return now - t < DAY;
  return now - t < 7 * DAY; // 7d
}

export interface AreaRollup {
  area: string;
  reports: number;
  withoutPower: number;
  withoutWater: number;
  both: number;
  urgent: number;
  latest: string; // ISO of most recent report in the area
}

export interface DashboardRollup {
  reports: ReportSummary[];
  metrics: { reports: number; withoutPower: number; withoutWater: number; urgent: number };
  areas: AreaRollup[];
  urgent: ReportSummary[];
}

function isNoPower(r: ReportSummary): boolean {
  return (r.service_type === 'electricity' && r.service_status === 'unavailable') || (r.tags ?? []).includes('no_power');
}
function isNoWater(r: ReportSummary): boolean {
  return (r.service_type === 'piped_water' && r.service_status === 'unavailable') || (r.tags ?? []).includes('no_water');
}

/**
 * Single source of truth for the dashboard: everything is derived client-side
 * from /reports filtered by the selected time range, so metric cards,
 * neighborhoods, and the urgent queue always agree. (The summary/areas API
 * endpoints don't take a range; the live feed filters itself by received_at.)
 */
export function useDashboardData(range: TimeRange, now: number = Date.now()): { data: DashboardRollup | undefined; isPending: boolean } {
  const reports = useReports();

  const data = useMemo<DashboardRollup | undefined>(() => {
    if (!reports.data) return undefined;
    const inRange = reports.data.filter((r) => withinRange(r.submitted_at, range, now));

    const byArea = new Map<string, AreaRollup>();
    let withoutPower = 0;
    let withoutWater = 0;
    let urgent = 0;
    for (const r of inRange) {
      const np = isNoPower(r);
      const nw = isNoWater(r);
      if (np) withoutPower++;
      if (nw) withoutWater++;
      if (r.urgent) urgent++;
      const area = r.area ?? '—';
      const a = byArea.get(area) ?? { area, reports: 0, withoutPower: 0, withoutWater: 0, both: 0, urgent: 0, latest: r.submitted_at };
      a.reports++;
      if (np) a.withoutPower++;
      if (nw) a.withoutWater++;
      if (np && nw) a.both++;
      if (r.urgent) a.urgent++;
      if (Date.parse(r.submitted_at) > Date.parse(a.latest)) a.latest = r.submitted_at;
      byArea.set(area, a);
    }

    const areas = [...byArea.values()].sort(
      (x, z) => z.urgent - x.urgent || z.withoutPower + z.withoutWater - (x.withoutPower + x.withoutWater) || z.reports - x.reports,
    );

    return {
      reports: inRange,
      metrics: { reports: inRange.length, withoutPower, withoutWater, urgent },
      areas,
      urgent: inRange.filter((r) => r.urgent),
    };
  }, [reports.data, range, now]);

  return { data, isPending: reports.isPending };
}
