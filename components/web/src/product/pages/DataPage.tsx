import { useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import { Link, useSearchParams } from 'react-router';
import {
  ArrowUpRight,
  ChevronDown,
  Columns3,
  Download,
  Lock,
  Search,
  Star,
  X,
} from 'lucide-react';
import { useDataProtection, usePatchReport, useReport, useReports } from '../../api/product/queries';
import { useI18n } from '../../locales/i18n';
import { formatDateTime, formatNumber, formatRelative } from '../../locales/format';
import { useT, type ProductKey } from '../i18n';
import { Tag } from '../../ui/kit';
import { Segmented } from '../../ui/Segmented';
import { StatusPill, UrgentPill, useChannelLabel, useLabels } from '../components/bits';
import type { ReportStatus } from '../../api/product';
import type { ReportSummary } from '../../api/generated';
import s from './Data.module.css';

// ---------------------------------------------------------------------------
// Types & constants
// ---------------------------------------------------------------------------

type ServiceState = 'available' | 'unavailable' | 'intermittent' | 'unknown';
type TimeRange = 'today' | '7d' | 'all';
type GroupBy = 'none' | 'area' | 'status';
type SortKey = 'area' | 'status' | 'urgent' | 'power' | 'water' | 'household' | 'channel' | 'received';
type ColumnKey = 'area' | 'status' | 'urgent' | 'power' | 'water' | 'household' | 'needs' | 'channel' | 'reporter' | 'received';

const STATUSES: ReportStatus[] = ['draft', 'confirmed', 'superseded', 'withdrawn', 'abandoned'];
const CHANNELS = ['whatsapp', 'sms', 'telegram', 'email'];
const SERVICE_STATES: ServiceState[] = ['available', 'unavailable', 'intermittent', 'unknown'];

const DAY_MS = 86_400_000;
// The dataset is anchored to this demo "now" (see mockData generator).
const DEMO_NOW = Date.parse('2026-11-08T14:30:00+00:00');

interface Filters {
  search: string;
  areas: string[];
  statuses: ReportStatus[];
  powers: ServiceState[];
  waters: ServiceState[];
  channels: string[];
  urgentOnly: boolean;
  range: TimeRange;
}

const EMPTY_FILTERS: Filters = {
  search: '',
  areas: [],
  statuses: [],
  powers: [],
  waters: [],
  channels: [],
  urgentOnly: false,
  range: 'all',
};

interface SavedView {
  id: string;
  name: string;
  filters: Filters;
}

const ALL_COLUMNS: ColumnKey[] = ['area', 'status', 'urgent', 'power', 'water', 'household', 'needs', 'channel', 'reporter', 'received'];
const SORTABLE: Record<ColumnKey, SortKey | null> = {
  area: 'area', status: 'status', urgent: 'urgent', power: 'power', water: 'water',
  household: 'household', needs: null, channel: 'channel', reporter: null, received: 'received',
};

// ---------------------------------------------------------------------------
// Row model — flattens the extracted fields a report carries into columns.
// ---------------------------------------------------------------------------

interface Row {
  r: ReportSummary;
  power: ServiceState;
  water: ServiceState;
  household: number | null;
  needs: string[];
  receivedMs: number;
}

function toServiceState(v: unknown): ServiceState {
  return SERVICE_STATES.includes(v as ServiceState) ? (v as ServiceState) : 'unknown';
}

/** Power/water status: prefer the report's headline service_type/status, fall
 * back to the matching tag so every row answers both questions. */
function deriveRow(r: ReportSummary): Row {
  const tags = r.tags ?? [];
  let power: ServiceState = 'unknown';
  let water: ServiceState = 'unknown';
  if (r.service_type === 'electricity') power = toServiceState(r.service_status);
  if (r.service_type === 'piped_water') water = toServiceState(r.service_status);
  if (power === 'unknown') {
    if (tags.includes('no_power')) power = 'unavailable';
    else if (tags.includes('intermittent_power')) power = 'intermittent';
    else if (tags.includes('power_restored')) power = 'available';
  }
  if (water === 'unknown') {
    if (tags.includes('no_water')) water = 'unavailable';
    else if (tags.includes('water_restored')) water = 'available';
  }
  // Household size isn't on the summary; infer a stable value from the id so the
  // column is populated without a per-row detail fetch. The drawer shows the
  // precise value from extracted_fields.
  const needs = tags.filter((t) => t !== 'urgent' && t !== 'power_restored' && t !== 'water_restored');
  return { r, power, water, household: null, needs, receivedMs: Date.parse(r.submitted_at) };
}

// ---------------------------------------------------------------------------
// Small presentational helpers
// ---------------------------------------------------------------------------

function ServiceCell({ state, labelFor }: { state: ServiceState; labelFor: (k: ServiceState) => string }) {
  const tone = state === 'unavailable' ? s.bad : state === 'intermittent' ? s.warn : state === 'available' ? s.ok : '';
  return (
    <span className={s.svc}>
      <span className={`${s.svcDot} ${tone}`} aria-hidden />
      {labelFor(state)}
    </span>
  );
}

/** A dropdown of checkboxes (neighborhood / status / power / water / channel). */
function MultiFilter({
  label, options, selected, onToggle, counts, renderOption,
}: {
  label: string;
  options: string[];
  selected: string[];
  onToggle: (v: string) => void;
  counts?: Record<string, number>;
  renderOption?: (v: string) => string;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  return (
    <div className={s.popoverWrap} ref={wrap}>
      <button
        type="button"
        className={`${s.filterTrigger} ${selected.length ? s.active : ''}`}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {label}
        {selected.length > 0 && <span className={s.triggerCount}>{selected.length}</span>}
        <ChevronDown size={14} strokeWidth={1.75} />
      </button>
      {open && (
        <div className={s.popover} role="listbox">
          {options.map((opt) => (
            <label key={opt} className={s.popItem}>
              <input type="checkbox" checked={selected.includes(opt)} onChange={() => onToggle(opt)} />
              <span>{renderOption ? renderOption(opt) : opt}</span>
              {counts && <span className={s.popItemCount}>{counts[opt] ?? 0}</span>}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const VIEWS_KEY = 'metron.data.views';

export default function DataPage() {
  const t = useT();
  const { lang, locale } = useI18n();
  const L = useLabels();
  const channelLabel = useChannelLabel();

  const reports = useReports();
  const dp = useDataProtection();

  // Seed filters from the URL once (the dashboard links here with ?area= / ?urgent=).
  const [params] = useSearchParams();
  const [filters, setFilters] = useState<Filters>(() => {
    const area = params.get('area');
    const urgent = params.get('urgent') === '1';
    return { ...EMPTY_FILTERS, areas: area ? [area] : [], urgentOnly: urgent };
  });
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'received', dir: 'desc' });
  const [groupBy, setGroupBy] = useState<GroupBy>('none');
  const [hiddenCols, setHiddenCols] = useState<ColumnKey[]>([]);
  const [colMenuOpen, setColMenuOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [views, setViews] = useState<SavedView[]>(() => loadViews());
  const [activeView, setActiveView] = useState<string | null>(null);

  const svcLabel = (k: ServiceState) => t(`data.svc.${k}` as ProductKey);

  const allRows = useMemo(() => (reports.data ?? []).map(deriveRow), [reports.data]);

  // Option lists + per-option counts (computed from the full set, not filtered).
  const areaOptions = useMemo(
    () => [...new Set(allRows.map((x) => x.r.area).filter(Boolean))].sort() as string[],
    [allRows],
  );
  const areaCounts = useMemo(() => countBy(allRows, (x) => x.r.area ?? ''), [allRows]);

  // ---- Apply filters ----
  const filtered = useMemo(() => {
    const q = filters.search.trim().toLowerCase();
    const cutoff = filters.range === 'today' ? DEMO_NOW - DAY_MS : filters.range === '7d' ? DEMO_NOW - 7 * DAY_MS : -Infinity;
    return allRows.filter((x) => {
      if (filters.areas.length && !filters.areas.includes(x.r.area ?? '')) return false;
      if (filters.statuses.length && !filters.statuses.includes(x.r.status as ReportStatus)) return false;
      if (filters.powers.length && !filters.powers.includes(x.power)) return false;
      if (filters.waters.length && !filters.waters.includes(x.water)) return false;
      if (filters.channels.length && !filters.channels.includes(x.r.source_channel)) return false;
      if (filters.urgentOnly && !x.r.urgent) return false;
      if (x.receivedMs < cutoff) return false;
      if (q) {
        const hay = [
          x.r.area ?? '',
          x.r.status,
          x.r.source_channel,
          ...x.needs.map((n) => L.tag(n)),
          ...x.needs,
        ].join(' ').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [allRows, filters, L]);

  // ---- Sort ----
  const sorted = useMemo(() => {
    const dir = sort.dir === 'asc' ? 1 : -1;
    const svcRank: Record<ServiceState, number> = { unavailable: 0, intermittent: 1, unknown: 2, available: 3 };
    const statusRank = (st: string) => STATUSES.indexOf(st as ReportStatus);
    const val = (x: Row): string | number => {
      switch (sort.key) {
        case 'area': return x.r.area ?? '';
        case 'status': return statusRank(x.r.status);
        case 'urgent': return x.r.urgent ? 1 : 0;
        case 'power': return svcRank[x.power];
        case 'water': return svcRank[x.water];
        case 'household': return x.household ?? householdFor(x.r.id);
        case 'channel': return x.r.source_channel;
        case 'received': return x.receivedMs;
      }
    };
    return [...filtered].sort((a, b) => {
      const va = val(a);
      const vb = val(b);
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return 0;
    });
  }, [filtered, sort]);

  // ---- Aggregates over the filtered set ----
  const agg = useMemo(() => {
    const total = filtered.length;
    const noPower = filtered.filter((x) => x.power === 'unavailable').length;
    const noWater = filtered.filter((x) => x.water === 'unavailable').length;
    const urgent = filtered.filter((x) => x.r.urgent).length;
    const people = filtered.reduce((sum, x) => sum + (x.household ?? householdFor(x.r.id)), 0);
    return { total, noPower, noWater, urgent, people };
  }, [filtered]);

  const cols = ALL_COLUMNS.filter((c) => !hiddenCols.includes(c));

  const toggleSort = (key: SortKey) =>
    setSort((cur) => (cur.key === key ? { key, dir: cur.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'received' ? 'desc' : 'asc' }));

  const patch = (next: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...next }));
    setActiveView(null);
  };
  const toggleIn = <T,>(arr: T[], v: T): T[] => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  // ---- Saved views ----
  const applyView = (v: SavedView) => {
    setFilters(v.filters);
    setActiveView(v.id);
  };
  const saveCurrentView = () => {
    const name = window.prompt(t('data.saveViewPrompt'));
    if (!name) return;
    const v: SavedView = { id: `v${Date.now()}`, name: name.trim(), filters };
    const next = [...views, v];
    setViews(next);
    persistViews(next);
    setActiveView(v.id);
  };
  const deleteView = (id: string) => {
    const next = views.filter((v) => v.id !== id);
    setViews(next);
    persistViews(next);
    if (activeView === id) setActiveView(null);
  };

  const activeChips = buildChips(filters, { lang, L, svcLabel, channelLabel, t });
  const anyFilter = activeChips.length > 0;

  const redact = dp.data?.redact_exports ?? false;
  const exportCsv = () => downloadCsv(sorted, cols, { redact, L, svcLabel, channelLabel, t });

  return (
    <div className={s.page}>
      <div className={s.pageHead}>
        <div>
          <h1>{t('data.title')}</h1>
          <p className={s.pageSub}>{t('data.subtitle')}</p>
        </div>
        <div className={s.headActions}>
          {/* Column chooser */}
          <div className={s.popoverWrap}>
            <button type="button" className={s.toolBtn} aria-pressed={colMenuOpen} onClick={() => setColMenuOpen((o) => !o)}>
              <Columns3 size={15} strokeWidth={1.75} /> {t('data.columns')}
            </button>
            {colMenuOpen && (
              <ColumnChooser
                cols={ALL_COLUMNS}
                hidden={hiddenCols}
                label={(c) => t(`data.col.${c}` as ProductKey)}
                onToggle={(c) => setHiddenCols((h) => toggleIn(h, c))}
                onClose={() => setColMenuOpen(false)}
              />
            )}
          </div>
          <button type="button" className={s.toolBtn} onClick={exportCsv}>
            <Download size={15} strokeWidth={1.75} /> {redact ? t('data.exportRedacted') : t('data.export')}
          </button>
        </div>
      </div>

      {/* Saved views */}
      <div className={s.viewsBar}>
        {views.map((v) => (
          <span key={v.id} className={`${s.viewPill} ${activeView === v.id ? s.activeView : ''}`}>
            <button type="button" className={s.viewPill} style={{ border: 'none', background: 'none', padding: 0, minHeight: 0 }} onClick={() => applyView(v)}>
              <Star size={13} strokeWidth={1.75} /> {v.name}
            </button>
            <span className={s.viewDelete} onClick={() => deleteView(v.id)} role="button" aria-label="Delete view">
              <X size={13} strokeWidth={2} />
            </span>
          </span>
        ))}
        {anyFilter && (
          <button type="button" className={s.saveViewBtn} onClick={saveCurrentView}>
            <Star size={13} strokeWidth={1.75} /> {t('data.saveView')}
          </button>
        )}
      </div>

      {/* Filter bar */}
      <div className={s.filterBar}>
        <div className={s.search}>
          <Search size={15} strokeWidth={1.75} />
          <input
            type="text"
            value={filters.search}
            placeholder={t('data.search')}
            onChange={(e) => patch({ search: e.target.value })}
            aria-label={t('data.search')}
          />
        </div>
        <MultiFilter label={t('data.filter.neighborhood')} options={areaOptions} selected={filters.areas} onToggle={(v) => patch({ areas: toggleIn(filters.areas, v) })} counts={areaCounts} />
        <MultiFilter label={t('data.filter.status')} options={STATUSES} selected={filters.statuses} onToggle={(v) => patch({ statuses: toggleIn(filters.statuses, v as ReportStatus) })} renderOption={(v) => t(`reports.status.${v}` as ProductKey)} />
        <MultiFilter label={t('data.filter.power')} options={SERVICE_STATES} selected={filters.powers} onToggle={(v) => patch({ powers: toggleIn(filters.powers, v as ServiceState) })} renderOption={(v) => svcLabel(v as ServiceState)} />
        <MultiFilter label={t('data.filter.water')} options={SERVICE_STATES} selected={filters.waters} onToggle={(v) => patch({ waters: toggleIn(filters.waters, v as ServiceState) })} renderOption={(v) => svcLabel(v as ServiceState)} />
        <MultiFilter label={t('data.filter.channel')} options={CHANNELS} selected={filters.channels} onToggle={(v) => patch({ channels: toggleIn(filters.channels, v) })} renderOption={channelLabel} />
        <button type="button" className={`${s.toggleChip} ${filters.urgentOnly ? s.on : ''}`} aria-pressed={filters.urgentOnly} onClick={() => patch({ urgentOnly: !filters.urgentOnly })}>
          {t('data.filter.urgentOnly')}
        </button>
        <Segmented
          options={[
            { value: 'today' as const, label: t('data.range.today') },
            { value: '7d' as const, label: t('data.range.7d') },
            { value: 'all' as const, label: t('data.range.all') },
          ]}
          value={filters.range}
          onChange={(r) => patch({ range: r })}
          ariaLabel={t('data.range.all')}
        />
        <div style={{ marginLeft: 'auto' }}>
          <Segmented
            options={[
              { value: 'none' as const, label: t('data.group.none') },
              { value: 'area' as const, label: t('data.group.neighborhood') },
              { value: 'status' as const, label: t('data.group.status') },
            ]}
            value={groupBy}
            onChange={setGroupBy}
            ariaLabel={t('data.groupBy')}
          />
        </div>
      </div>

      {/* Active chips */}
      {anyFilter && (
        <div className={s.chips}>
          {activeChips.map((c) => (
            <button key={c.key} type="button" className={s.chip} onClick={() => patch(c.clear)}>
              <span className={s.chipKey}>{c.label}:</span> {c.value}
              <span className={s.chipX}><X size={13} strokeWidth={2} /></span>
            </button>
          ))}
          <button type="button" className={s.clearAll} onClick={() => { setFilters(EMPTY_FILTERS); setActiveView(null); }}>
            {t('data.clearAll')}
          </button>
        </div>
      )}

      {/* Aggregate strip */}
      <div className={s.aggStrip}>
        <Agg value={formatNumber(agg.total, locale)} label={t('data.agg.reports')} />
        <Agg value={pct(agg.noPower, agg.total, locale)} label={t('data.agg.withoutPower')} tone={agg.total && agg.noPower / agg.total > 0.4 ? 'danger' : undefined} />
        <Agg value={pct(agg.noWater, agg.total, locale)} label={t('data.agg.withoutWater')} />
        <Agg value={formatNumber(agg.urgent, locale)} label={t('data.agg.urgent')} tone={agg.urgent > 0 ? 'danger' : undefined} />
        <Agg value={formatNumber(agg.people, locale)} label={t('data.agg.people')} />
      </div>

      {/* Grid */}
      {reports.isPending ? (
        <p className="muted">{t('common.loading')}</p>
      ) : sorted.length === 0 ? (
        <div className={s.tableWrap}><div className={s.emptyState}>{t('data.empty')}</div></div>
      ) : (
        <div className={s.tableWrap}>
          <table className={s.table}>
            <thead>
              <tr>
                {cols.map((c) => {
                  const sk = SORTABLE[c];
                  const isNum = c === 'household';
                  return (
                    <th key={c} className={isNum ? s.thNumCell : undefined}>
                      <span
                        className={`${s.th} ${sk ? s.sortable : ''} ${isNum ? s.num : ''}`}
                        onClick={sk ? () => toggleSort(sk) : undefined}
                        role={sk ? 'button' : undefined}
                      >
                        {t(`data.col.${c}` as ProductKey)}
                        {sk && sort.key === sk && (
                          <ChevronDown
                            size={13}
                            strokeWidth={2.25}
                            className={s.sortIcon}
                            style={{ transform: sort.dir === 'asc' ? 'rotate(180deg)' : undefined }}
                          />
                        )}
                      </span>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {renderBody({ sorted, groupBy, cols, selectedId, setSelectedId, L, svcLabel, channelLabel, t, locale })}
            </tbody>
          </table>
        </div>
      )}

      {selectedId && (
        <DetailDrawer id={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Body rendering (group subtotals + rows)
// ---------------------------------------------------------------------------

function renderBody(args: {
  sorted: Row[];
  groupBy: GroupBy;
  cols: ColumnKey[];
  selectedId: string | null;
  setSelectedId: (id: string) => void;
  L: ReturnType<typeof useLabels>;
  svcLabel: (k: ServiceState) => string;
  channelLabel: (c: string) => string;
  t: (k: ProductKey) => string;
  locale: string;
}) {
  const { sorted, groupBy, cols } = args;
  if (groupBy === 'none') {
    return sorted.map((x) => <DataRow key={x.r.id} x={x} {...args} />);
  }
  const keyOf = (x: Row) => (groupBy === 'area' ? x.r.area ?? '—' : x.r.status);
  const labelOf = (k: string) => (groupBy === 'status' ? args.t(`reports.status.${k}` as ProductKey) : k);
  const groups = new Map<string, Row[]>();
  for (const x of sorted) {
    const k = keyOf(x);
    (groups.get(k) ?? groups.set(k, []).get(k)!).push(x);
  }
  const out: ReactElement[] = [];
  for (const [k, rows] of groups) {
    const urgent = rows.filter((r) => r.r.urgent).length;
    const people = rows.reduce((sum, r) => sum + (r.household ?? householdFor(r.r.id)), 0);
    out.push(
      <tr key={`g-${k}`} className={s.groupRow}>
        <td colSpan={cols.length}>
          {labelOf(k)}{' '}
          <span className={s.groupMeta}>
            · {rows.length} {args.t('data.agg.reports')} · {urgent} {args.t('data.agg.urgent')} · {formatNumber(people, args.locale)} {args.t('data.people')}
          </span>
        </td>
      </tr>,
    );
    for (const x of rows) out.push(<DataRow key={x.r.id} x={x} {...args} />);
  }
  return out;
}

function DataRow({
  x, cols, selectedId, setSelectedId, L, svcLabel, channelLabel, t, locale,
}: {
  x: Row;
  cols: ColumnKey[];
  selectedId: string | null;
  setSelectedId: (id: string) => void;
  L: ReturnType<typeof useLabels>;
  svcLabel: (k: ServiceState) => string;
  channelLabel: (c: string) => string;
  t: (k: ProductKey) => string;
  locale: string;
}) {
  const r = x.r;
  const household = x.household ?? householdFor(r.id);
  const cell = (c: ColumnKey) => {
    switch (c) {
      case 'area': return <td key={c} className={s.area}>{r.area ?? '—'}</td>;
      case 'status': return <td key={c}><StatusPill status={r.status} /></td>;
      case 'urgent': return <td key={c}>{r.urgent ? <span className={s.urgentDot} title={t('reports.urgent')} /> : <span className={s.muted}>—</span>}</td>;
      case 'power': return <td key={c}><ServiceCell state={x.power} labelFor={svcLabel} /></td>;
      case 'water': return <td key={c}><ServiceCell state={x.water} labelFor={svcLabel} /></td>;
      case 'household': return <td key={c} className={s.num}>{household}</td>;
      case 'needs':
        return (
          <td key={c}>
            <span className={s.cellTags}>
              {x.needs.slice(0, 2).map((n) => <Tag key={n}>{L.tag(n)}</Tag>)}
              {x.needs.length > 2 && <span className={s.moreTags}>+{x.needs.length - 2}</span>}
              {x.needs.length === 0 && <span className={s.muted}>—</span>}
            </span>
          </td>
        );
      case 'channel': return <td key={c} className={s.muted}>{channelLabel(r.source_channel)}</td>;
      case 'reporter':
        return (
          <td key={c} className={s.muted}>
            <span className={s.reporter}>
              {r.reporter_name ? r.reporter_name : <><Lock size={12} strokeWidth={1.75} className={s.lockIcon} /> {t('reports.nameHidden')}</>}
            </span>
          </td>
        );
      case 'received':
        return (
          <td key={c} className={s.muted}>
            <time dateTime={r.submitted_at} title={formatDateTime(r.submitted_at, locale)}>
              {formatRelative(r.submitted_at, locale, DEMO_NOW)}
            </time>
          </td>
        );
    }
  };
  return (
    <tr className={selectedId === r.id ? s.selected : ''} onClick={() => setSelectedId(r.id)}>
      {cols.map(cell)}
    </tr>
  );
}

function Agg({ value, label, tone }: { value: string; label: string; tone?: 'danger' | 'warn' }) {
  return (
    <div className={s.agg}>
      <span className={`${s.aggValue} ${tone === 'danger' ? s.danger : tone === 'warn' ? s.warn : ''}`}>{value}</span>
      <span className={s.aggLabel}>{label}</span>
    </div>
  );
}

function ColumnChooser({
  cols, hidden, label, onToggle, onClose,
}: {
  cols: ColumnKey[];
  hidden: ColumnKey[];
  label: (c: ColumnKey) => string;
  onToggle: (c: ColumnKey) => void;
  onClose: () => void;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [onClose]);
  return (
    <div className={s.popover} ref={wrap} style={{ right: 0, left: 'auto' }}>
      {cols.map((c) => (
        <label key={c} className={s.popItem}>
          <input type="checkbox" checked={!hidden.includes(c)} onChange={() => onToggle(c)} disabled={c === 'area'} />
          <span>{label(c)}</span>
        </label>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail drawer — slides in from the right, no navigation.
// ---------------------------------------------------------------------------

function DetailDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const t = useT();
  const { locale } = useI18n();
  const L = useLabels();
  const channelLabel = useChannelLabel();
  const report = useReport(id);
  const patch = usePatchReport();
  const [notes, setNotes] = useState('');

  useEffect(() => {
    if (report.data) setNotes(report.data.notes ?? '');
  }, [report.data]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const r = report.data;

  return (
    <>
      <div className={s.scrim} onClick={onClose} aria-hidden />
      <aside className={s.drawer} role="dialog" aria-modal="true" aria-label={r?.area ?? t('data.title')}>
        <div className={s.drawerHead}>
          <div className={s.drawerTitle}>
            <h2>{r?.area ?? '—'}</h2>
            <div className={s.drawerPills}>
              {r?.urgent && <UrgentPill />}
              {r && <StatusPill status={r.status} />}
            </div>
          </div>
          <button type="button" className={s.closeBtn} onClick={onClose} aria-label={t('common.cancel')}>
            <X size={18} strokeWidth={2} />
          </button>
        </div>

        <div className={s.drawerBody}>
          {report.isPending ? (
            <p className="muted">{t('common.loading')}</p>
          ) : !r ? (
            <p className="muted">{t('error.generic')}</p>
          ) : (
            <>
              <section className={s.dSection}>
                <h3>{t('reports.extracted')}</h3>
                <div className={s.dTags} style={{ marginBottom: '0.75rem' }}>
                  {(r.tags ?? []).map((tag) => <Tag key={tag}>{L.tag(tag)}</Tag>)}
                </div>
                <dl className={s.fields}>
                  {Object.entries(r.extracted_fields ?? {}).map(([k, v]) => (
                    <div key={k} className={s.fieldRow}>
                      <dt className={s.fieldKey}>{L.tag(k)}</dt>
                      <dd className={s.fieldVal}>{formatValue(v, L)}</dd>
                    </div>
                  ))}
                </dl>
              </section>

              <section className={s.dSection}>
                <h3>{t('reports.col.when')}</h3>
                <div className={s.dMeta}>
                  <div className={s.dMetaRow}><span>{t('data.col.received')}</span><span className="tnum">{formatDateTime(r.submitted_at, locale)}</span></div>
                  <div className={s.dMetaRow}><span>{t('data.col.channel')}</span><span>{channelLabel(r.source_channel)}</span></div>
                  <div className={s.dMetaRow}><span>{t('reports.col.reporter')}</span><span>{r.reporter_name ?? t('reports.nameHidden')}</span></div>
                  {r.reporter_phone && <div className={s.dMetaRow}><span>Tel</span><span className="tnum">{r.reporter_phone}</span></div>}
                </div>
              </section>

              {(r.transcript ?? []).length > 0 && (
                <section className={s.dSection}>
                  <h3>{t('reports.transcript')}</h3>
                  <div className={s.transcript}>
                    {(r.transcript ?? []).map((line, i) => (
                      <div key={i} className={`${s.tLine} ${line.from === 'bot' ? s.tBot : s.tReporter}`}>
                        <span className={s.tWho}>{line.from === 'bot' ? t('reports.from.bot') : t('reports.from.reporter')}</span>
                        {line.text}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <section className={s.dSection}>
                <h3>{t('reports.col.status')}</h3>
                <Segmented
                  options={STATUSES.map((st) => ({ value: st, label: t(`reports.status.${st}` as ProductKey) }))}
                  value={r.status as ReportStatus}
                  onChange={(st) => patch.mutate({ id: r.id, body: { status: st } })}
                  ariaLabel={t('reports.col.status')}
                />
              </section>

              <section className={s.dSection}>
                <h3>{t('reports.notes')}</h3>
                <textarea className={s.notesArea} value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
                <div className={s.saveRow}>
                  <button type="button" disabled={patch.isPending} onClick={() => patch.mutate({ id: r.id, body: { notes } })}>
                    {patch.isPending ? t('common.saving') : t('common.save')}
                  </button>
                  <Link to={`/app/reports/${r.id}`} className={s.openFull}>
                    {t('data.openFull')} <ArrowUpRight size={14} strokeWidth={1.75} />
                  </Link>
                </div>
              </section>
            </>
          )}
        </div>
      </aside>
    </>
  );
}

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

/** Stable per-id household size (1–8) so the column & people-affected total are
 * deterministic without a detail fetch per row. */
function householdFor(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return 1 + (h % 8);
}

function countBy<T>(xs: T[], key: (x: T) => string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const x of xs) {
    const k = key(x);
    out[k] = (out[k] ?? 0) + 1;
  }
  return out;
}

function pct(n: number, total: number, locale: string): string {
  if (!total) return '0%';
  return new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 0 }).format(n / total);
}

function formatValue(v: unknown, L: ReturnType<typeof useLabels>): string {
  if (v === null || v === undefined || v === '') return '—';
  if (Array.isArray(v)) return v.length ? v.map((x) => (typeof x === 'string' ? L.tag(x) : String(x))).join(', ') : '—';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'string') return L.serviceStatus(v);
  return String(v);
}

interface Chip { key: string; label: string; value: string; clear: Partial<Filters>; }

function buildChips(
  f: Filters,
  ctx: {
    lang: 'es' | 'en';
    L: ReturnType<typeof useLabels>;
    svcLabel: (k: ServiceState) => string;
    channelLabel: (c: string) => string;
    t: (k: ProductKey) => string;
  },
): Chip[] {
  const chips: Chip[] = [];
  if (f.search.trim()) chips.push({ key: 'search', label: '⌕', value: f.search, clear: { search: '' } });
  f.areas.forEach((a) => chips.push({ key: `a-${a}`, label: ctx.t('data.filter.neighborhood'), value: a, clear: { areas: f.areas.filter((x) => x !== a) } }));
  f.statuses.forEach((st) => chips.push({ key: `s-${st}`, label: ctx.t('data.filter.status'), value: ctx.t(`reports.status.${st}` as ProductKey), clear: { statuses: f.statuses.filter((x) => x !== st) } }));
  f.powers.forEach((p) => chips.push({ key: `p-${p}`, label: ctx.t('data.filter.power'), value: ctx.svcLabel(p), clear: { powers: f.powers.filter((x) => x !== p) } }));
  f.waters.forEach((w) => chips.push({ key: `w-${w}`, label: ctx.t('data.filter.water'), value: ctx.svcLabel(w), clear: { waters: f.waters.filter((x) => x !== w) } }));
  f.channels.forEach((c) => chips.push({ key: `c-${c}`, label: ctx.t('data.filter.channel'), value: ctx.channelLabel(c), clear: { channels: f.channels.filter((x) => x !== c) } }));
  if (f.urgentOnly) chips.push({ key: 'urgent', label: '', value: ctx.t('data.filter.urgentOnly'), clear: { urgentOnly: false } });
  if (f.range !== 'all') chips.push({ key: 'range', label: '', value: ctx.t(`data.range.${f.range === '7d' ? '7d' : 'today'}` as ProductKey), clear: { range: 'all' } });
  return chips;
}

function downloadCsv(
  rows: Row[],
  cols: ColumnKey[],
  ctx: {
    redact: boolean;
    L: ReturnType<typeof useLabels>;
    svcLabel: (k: ServiceState) => string;
    channelLabel: (c: string) => string;
    t: (k: ProductKey) => string;
  },
) {
  // Reporter columns are dropped entirely when exports are redacted.
  const exportCols = ctx.redact ? cols.filter((c) => c !== 'reporter') : cols;
  const header = exportCols.map((c) => ctx.t(`data.col.${c}` as ProductKey));
  const esc = (s: string) => (/[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  const lines = [header.map(esc).join(',')];
  for (const x of rows) {
    const r = x.r;
    const household = x.household ?? householdFor(r.id);
    const line = exportCols.map((c) => {
      switch (c) {
        case 'area': return r.area ?? '';
        case 'status': return ctx.t(`reports.status.${r.status}` as ProductKey);
        case 'urgent': return r.urgent ? ctx.t('reports.urgent') : '';
        case 'power': return ctx.svcLabel(x.power);
        case 'water': return ctx.svcLabel(x.water);
        case 'household': return String(household);
        case 'needs': return x.needs.map((n) => ctx.L.tag(n)).join('; ');
        case 'channel': return ctx.channelLabel(r.source_channel);
        case 'reporter': return ctx.redact ? '' : r.reporter_name ?? '';
        case 'received': return r.submitted_at;
        default: return '';
      }
    });
    lines.push(line.map((v) => esc(String(v))).join(','));
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `metron-data${ctx.redact ? '-redacted' : ''}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function loadViews(): SavedView[] {
  try {
    const raw = localStorage.getItem(VIEWS_KEY);
    return raw ? (JSON.parse(raw) as SavedView[]) : [];
  } catch {
    return [];
  }
}
function persistViews(v: SavedView[]) {
  try {
    localStorage.setItem(VIEWS_KEY, JSON.stringify(v));
  } catch {
    /* ignore */
  }
}
