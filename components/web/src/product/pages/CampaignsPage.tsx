import { useRef, useState } from 'react';
import {
  Check, ChevronLeft, Mail, MessageCircle, MessageSquare, Send,
} from 'lucide-react';
import { useI18n } from '../../locales/i18n';
import { formatDate } from '../../locales/format';
import {
  useCampaigns, useCollectionTemplates, useCreateCampaign, useSuggestCampaignFields,
} from '../../api/product/queries';
import { useT, type ProductKey } from '../i18n';
import { Icon } from '../../ui/Icon';
import { Pill } from '../../ui/kit';
import { Segmented } from '../../ui/Segmented';
import type { Campaign, CampaignField } from '../../api/product';
import { assumeCountryCode, classify, splitPasted, summarize, type ParsedNumber } from './phone';
import s from './Pages.module.css';
import w from './CampaignWizard.module.css';

type StepId = 'about' | 'ask' | 'channel';
const STEPS: StepId[] = ['about', 'ask', 'channel'];

export default function CampaignsPage() {
  const t = useT();
  const campaigns = useCampaigns();
  const templates = useCollectionTemplates();
  const { locale } = useI18n();

  return (
    <>
      <div className={s.head}>
        <h1>{t('campaigns.title')}</h1>
      </div>

      <div className={w.layout}>
        <div>
          <p className={w.listTitle}>{t('campaigns.title')}</p>
          {campaigns.isPending ? (
            <p className="muted">{t('common.loading')}</p>
          ) : !campaigns.data || campaigns.data.length === 0 ? (
            <p className="muted">{t('campaigns.empty')}</p>
          ) : (
            <div className={s.campaignGroup}>
              {campaigns.data.map((c) => (
                <CampaignRow key={c.id} c={c} locale={locale}
                  sentLabel={t('campaigns.sent')} repliedLabel={t('campaigns.replied')}
                  statusLabel={t('campaigns.status.active')} />
              ))}
            </div>
          )}
        </div>

        <Wizard
          defaultTemplateId={templates.data?.[0]?.id ?? 'power_water_outages'}
          onCreated={() => campaigns.refetch()}
        />
      </div>
    </>
  );
}

// ===========================================================================
// Wizard
// ===========================================================================

function Wizard({ defaultTemplateId, onCreated }: { defaultTemplateId: string; onCreated: () => void }) {
  const t = useT();
  const suggest = useSuggestCampaignFields();
  const create = useCreateCampaign();

  const [step, setStep] = useState<StepId>('about');
  const idx = STEPS.indexOf(step);

  // Step 1
  const [name, setName] = useState('');
  const [purpose, setPurpose] = useState('');
  // Step 2
  const [fields, setFields] = useState<CampaignField[]>([]);
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
  const [fieldsSource, setFieldsSource] = useState<'llm' | 'fallback' | null>(null);
  // Step 3
  const [channel, setChannel] = useState<'whatsapp' | null>(null);
  const [numbers, setNumbers] = useState<ParsedNumber[]>([]);
  const [consent, setConsent] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const goAsk = async () => {
    if (!name.trim()) { setErr(t('onb.err.name')); return; }
    setErr(null);
    setStep('ask');
    // Fetch suggestions when entering step 2 (only once per campaign draft).
    if (fields.length === 0) {
      try {
        const res = await suggest.mutateAsync({
          name: name.trim(), purpose: purpose.trim(), collection_template_id: defaultTemplateId,
        });
        setFields(res.fields);
        setFieldsSource(res.source);
        const init: Record<string, boolean> = {};
        res.fields.forEach((f) => { init[f.id] = f.id === 'area' ? true : f.recommended; });
        setEnabled(init);
      } catch {
        setErr(t('error.generic'));
      }
    }
  };

  const launch = async () => {
    setErr(null);
    const selected = fields.filter((f) => f.id === 'area' || enabled[f.id]);
    try {
      await create.mutateAsync({
        name: name.trim(),
        collection_template_id: defaultTemplateId,
        areas: [],
        starts_at: null,
        ends_at: null,
        fields: selected,
      });
      onCreated();
      // Reset to a fresh draft.
      setStep('about'); setName(''); setPurpose('');
      setFields([]); setEnabled({}); setFieldsSource(null);
      setChannel(null); setNumbers([]); setConsent(false);
    } catch {
      setErr(t('error.generic'));
    }
  };

  const validCount = numbers.filter((n) => n.status === 'valid').length;
  const canLaunch = channel === 'whatsapp' && consent && validCount > 0 && !create.isPending;

  return (
    <div className={w.card}>
      <div className={w.topBar}>
        {idx > 0 && (
          <button type="button" className={w.back} onClick={() => setStep(STEPS[idx - 1]!)}>
            <Icon as={ChevronLeft} size={18} />{t('common.back')}
          </button>
        )}
        <div className={w.steps} aria-hidden>
          {STEPS.map((st, i) => (
            <span key={st} className={`${w.stepDot} ${i === idx ? w.stepDotActive : i < idx ? w.stepDotDone : ''}`} />
          ))}
        </div>
      </div>

      {err && <div className={w.err} role="alert">{err}</div>}

      {step === 'about' && (
        <AboutStep
          name={name} setName={setName} purpose={purpose} setPurpose={setPurpose} onNext={goAsk}
        />
      )}
      {step === 'ask' && (
        <AskStep
          loading={suggest.isPending}
          fields={fields}
          enabled={enabled}
          source={fieldsSource}
          onToggle={(id) => setEnabled((e) => ({ ...e, [id]: !e[id] }))}
          onNext={() => setStep('channel')}
        />
      )}
      {step === 'channel' && (
        <ChannelStep
          channel={channel} setChannel={setChannel}
          numbers={numbers} setNumbers={setNumbers}
          consent={consent} setConsent={setConsent}
          canLaunch={canLaunch} launching={create.isPending} onLaunch={launch}
        />
      )}
    </div>
  );
}

// ---- Step 1: About --------------------------------------------------------

function AboutStep({ name, setName, purpose, setPurpose, onNext }: {
  name: string; setName: (v: string) => void;
  purpose: string; setPurpose: (v: string) => void;
  onNext: () => void;
}) {
  const t = useT();
  return (
    <>
      <h2 className={w.title}>{t('cw.step.about')}</h2>
      <div className={w.field}>
        <label htmlFor="cw-name">{t('cw.about.name')}</label>
        <input
          id="cw-name" value={name} autoFocus
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); onNext(); } }}
          placeholder={t('cw.about.namePlaceholder')}
        />
      </div>
      <div className={w.field}>
        <label htmlFor="cw-purpose">{t('cw.about.purpose')}</label>
        <textarea
          id="cw-purpose" value={purpose} rows={4}
          onChange={(e) => setPurpose(e.target.value)}
          placeholder={t('cw.about.purposePlaceholder')}
        />
      </div>
      <div className={w.nav}>
        <button type="button" onClick={onNext} disabled={!name.trim()}>{t('common.next')}</button>
      </div>
    </>
  );
}

// ---- Step 2: Ask (field suggestions) --------------------------------------

function AskStep({ loading, fields, enabled, source, onToggle, onNext }: {
  loading: boolean;
  fields: CampaignField[];
  enabled: Record<string, boolean>;
  source: 'llm' | 'fallback' | null;
  onToggle: (id: string) => void;
  onNext: () => void;
}) {
  const t = useT();
  const kindLabel = (f: CampaignField): string =>
    t(`cw.kind.${f.kind}` as ProductKey);

  return (
    <>
      <h2 className={w.title}>{t('cw.step.ask')}</h2>
      <p className={w.sub}>
        {t('cw.ask.sub')}
        {source && <> · <span className="muted">{source === 'llm' ? t('cw.ask.aiNote') : t('cw.ask.templateNote')}</span></>}
      </p>

      {loading ? (
        <p className="muted">{t('cw.ask.loading')}</p>
      ) : (
        <div className={w.group}>
          {fields.map((f) => {
            const locked = f.id === 'area';
            const on = locked ? true : !!enabled[f.id];
            return (
              <div key={f.id} className={w.row}>
                <div className={w.rowBody}>
                  <div className={w.rowLabel}>
                    {f.label_en || f.id}
                    <span className={w.kindTag}>{kindLabel(f)}</span>
                    {f.recommended && !locked && <span className={w.recTag}>{t('cw.ask.recommended')}</span>}
                  </div>
                  {f.rationale && <div className={w.rowSub}>{f.rationale}</div>}
                </div>
                {locked ? (
                  <span className={w.lockedNote}>{t('cw.ask.areaLocked')}</span>
                ) : (
                  <button
                    type="button"
                    className={`${w.toggle} ${on ? w.toggleOn : ''}`}
                    aria-pressed={on}
                    aria-label={f.label_en || f.id}
                    onClick={() => onToggle(f.id)}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className={w.nav}>
        <button type="button" onClick={onNext} disabled={loading || fields.length === 0}>
          {t('common.next')}
        </button>
      </div>
    </>
  );
}

// ---- Step 3: Channel & contacts -------------------------------------------

const CHANNELS = [
  { id: 'whatsapp', icon: MessageCircle, enabled: true },
  { id: 'sms', icon: MessageSquare, enabled: false },
  { id: 'signal', icon: Send, enabled: false },
  { id: 'telegram', icon: Send, enabled: false },
  { id: 'email', icon: Mail, enabled: false },
] as const;

function ChannelStep({
  channel, setChannel, numbers, setNumbers, consent, setConsent, canLaunch, launching, onLaunch,
}: {
  channel: 'whatsapp' | null;
  setChannel: (v: 'whatsapp' | null) => void;
  numbers: ParsedNumber[];
  setNumbers: (v: ParsedNumber[]) => void;
  consent: boolean;
  setConsent: (v: boolean) => void;
  canLaunch: boolean;
  launching: boolean;
  onLaunch: () => void;
}) {
  const t = useT();

  const channelLabel = (id: string): string => {
    const key = `channel.${id}` as ProductKey;
    return t(key);
  };

  return (
    <>
      <h2 className={w.title}>{t('cw.step.channel')}</h2>

      <p className={w.groupTitle}>{t('cw.ch.title')}</p>
      <div className={w.group}>
        {CHANNELS.map((c) => {
          const selected = c.enabled && channel === c.id;
          return (
            <button
              key={c.id}
              type="button"
              className={w.chanRow}
              disabled={!c.enabled}
              aria-pressed={selected}
              onClick={() => c.enabled && setChannel(channel === 'whatsapp' ? null : 'whatsapp')}
            >
              <Icon as={c.icon} size={20} className={w.rowIcon} />
              <span className={w.chanName}>{channelLabel(c.id)}</span>
              {!c.enabled && <span className={w.soon}>{t('common.comingSoon')}</span>}
              {selected && <Icon as={Check} size={18} className={w.chanSel} />}
            </button>
          );
        })}
      </div>

      {channel === 'whatsapp' && (
        <ContactsPicker numbers={numbers} setNumbers={setNumbers} />
      )}

      <label className={w.consent}>
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>{t('cw.consent')}</span>
      </label>

      <div className={w.nav}>
        <button type="button" onClick={onLaunch} disabled={!canLaunch}>
          {launching ? t('cw.launching') : t('cw.launch')}
        </button>
      </div>
    </>
  );
}

// ---- Contacts picker (upload / paste / manual) ----------------------------

type ContactMode = 'upload' | 'paste' | 'manual';

function ContactsPicker({ numbers, setNumbers }: {
  numbers: ParsedNumber[]; setNumbers: (v: ParsedNumber[]) => void;
}) {
  const t = useT();
  const [mode, setMode] = useState<ContactMode>('upload');

  const summary = summarize(numbers.map((n) => n.raw));

  const setFromRaw = (raws: string[]) => setNumbers(raws.map(classify));

  return (
    <>
      <p className={w.groupTitle}>{t('cw.ct.title')}</p>
      <div className={w.segWrap}>
        <Segmented<ContactMode>
          ariaLabel={t('cw.ct.title')}
          value={mode}
          onChange={setMode}
          options={[
            { value: 'upload', label: t('cw.ct.upload') },
            { value: 'paste', label: t('cw.ct.paste') },
            { value: 'manual', label: t('cw.ct.manual') },
          ]}
        />
      </div>

      {mode === 'upload' && <UploadPane onNumbers={setFromRaw} />}
      {mode === 'paste' && <PastePane onNumbers={setFromRaw} />}
      {mode === 'manual' && <ManualPane numbers={numbers} setNumbers={setNumbers} />}

      <p className={w.helper}>{t('cw.ct.helper')}</p>

      {numbers.length > 0 && (
        <ResultSummary summary={summary} numbers={numbers} setNumbers={setNumbers} />
      )}
    </>
  );
}

function UploadPane({ onNumbers }: { onNumbers: (raws: string[]) => void }) {
  const t = useT();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [rows, setRows] = useState<string[][]>([]);
  const [headers, setHeaders] = useState<string[]>([]);
  const [colIdx, setColIdx] = useState<number | null>(null);

  const emit = (grid: string[][], col: number) => {
    const body = grid.slice(1); // drop header row
    onNumbers(body.map((r) => r[col] ?? '').filter((v) => v.trim() !== ''));
  };

  const parseFile = async (file: File) => {
    // Load SheetJS on demand so it isn't in the route's initial payload.
    const { read: xlsxRead, utils: xlsxUtils } = await import('xlsx');
    const buf = await file.arrayBuffer();
    const wb = xlsxRead(buf, { type: 'array' });
    const sheetName = wb.SheetNames[0];
    const sheet = sheetName ? wb.Sheets[sheetName] : undefined;
    if (!sheet) return;
    const grid = xlsxUtils.sheet_to_json<string[]>(sheet, { header: 1, blankrows: false, raw: false });
    const normalized = grid.map((r) => (r ?? []).map((c) => (c == null ? '' : String(c))));
    if (normalized.length === 0) return;
    const hdr = normalized[0]!;
    setHeaders(hdr);
    setRows(normalized);
    // Auto-pick a phone-looking column; else first column.
    const guess = hdr.findIndex((h) => /phone|tel|whatsapp|número|numero|cel/i.test(h));
    const col = guess >= 0 ? guess : 0;
    setColIdx(col);
    emit(normalized, col);
  };

  const onFiles = (files: FileList | null) => {
    const f = files?.[0];
    if (f) void parseFile(f);
  };

  return (
    <>
      <div
        className={`${w.drop} ${dragging ? w.dropActive : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); onFiles(e.dataTransfer.files); }}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click(); }}
      >
        <div className={w.dropMain}>{t('cw.ct.dropzone')}</div>
        <div className={w.dropHint}>{t('cw.ct.dropzoneHint')}</div>
        <input
          ref={inputRef} type="file" hidden accept=".csv,.xlsx,.xls"
          onChange={(e) => onFiles(e.target.files)}
        />
      </div>

      {headers.length > 1 && (
        <>
          <p className={w.helper}>{t('cw.ct.pickColumn')}</p>
          <div style={{ overflowX: 'auto' }}>
            <table className={w.previewTable}>
              <thead>
                <tr>
                  {headers.map((h, i) => (
                    <th
                      key={i}
                      className={`${w.colPick} ${colIdx === i ? w.colPickOn : ''}`}
                      onClick={() => { setColIdx(i); emit(rows, i); }}
                    >
                      {h || `#${i + 1}`}{colIdx === i ? ' ✓' : ''}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(1, 6).map((r, ri) => (
                  <tr key={ri}>{headers.map((_, ci) => <td key={ci}>{r[ci] ?? ''}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

function PastePane({ onNumbers }: { onNumbers: (raws: string[]) => void }) {
  const t = useT();
  const [text, setText] = useState('');
  return (
    <div className={w.field}>
      <textarea
        value={text} rows={4}
        placeholder={t('cw.ct.pastePlaceholder')}
        onChange={(e) => { setText(e.target.value); onNumbers(splitPasted(e.target.value)); }}
      />
    </div>
  );
}

function ManualPane({ numbers, setNumbers }: {
  numbers: ParsedNumber[]; setNumbers: (v: ParsedNumber[]) => void;
}) {
  const t = useT();
  const [val, setVal] = useState('');
  const add = () => {
    if (!val.trim()) return;
    setNumbers([...numbers, classify(val)]);
    setVal('');
  };
  return (
    <div className={w.manualRow}>
      <input
        value={val}
        placeholder={t('cw.ct.manualPlaceholder')}
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
      />
      <button type="button" className={w.miniBtn} onClick={add}>{t('cw.ct.manualAdd')}</button>
    </div>
  );
}

function ResultSummary({ summary, numbers, setNumbers }: {
  summary: ReturnType<typeof summarize>;
  numbers: ParsedNumber[];
  setNumbers: (v: ParsedNumber[]) => void;
}) {
  const t = useT();
  const needsFix = numbers.filter((n) => n.status === 'missing_country_code' || n.status === 'invalid');

  const assumeUs = () => setNumbers(assumeCountryCode(numbers, '+1'));

  const editAt = (raw: string, next: string) =>
    setNumbers(numbers.map((n) => (n.raw === raw ? classify(next) : n)));
  const removeAt = (raw: string) =>
    setNumbers(numbers.filter((n) => n.raw !== raw));

  return (
    <>
      <div className={w.summary}>
        <span className={`${w.summaryStat} ${w.summaryOk}`}>{summary.valid.length} {t('cw.ct.valid')}</span>
        {summary.needsCountryCode.length > 0 && (
          <span className={`${w.summaryStat} ${w.summaryWarn}`}>· {summary.needsCountryCode.length} {t('cw.ct.missingCode')}</span>
        )}
        {summary.invalid.length > 0 && (
          <span className={`${w.summaryStat} ${w.summaryBad}`}>· {summary.invalid.length} {t('cw.ct.invalid')}</span>
        )}
        {summary.duplicatesRemoved > 0 && (
          <span className={`${w.summaryStat} ${w.summaryMuted}`}>· {summary.duplicatesRemoved} {t('cw.ct.dupsRemoved')}</span>
        )}
      </div>

      {needsFix.length > 0 && (
        <div className={w.fixBlock}>
          <div className={w.fixHead}>
            <span className={w.fixTitle}>{t('cw.ct.needsFix')}</span>
            {summary.needsCountryCode.length > 0 && (
              <button type="button" className={w.miniBtn} onClick={assumeUs}>{t('cw.ct.assumeUs')}</button>
            )}
          </div>
          <div className={w.fixList}>
            {needsFix.map((n) => (
              <div key={n.raw} className={w.fixRow}>
                <input
                  defaultValue={n.raw}
                  onBlur={(e) => { if (e.target.value !== n.raw) editAt(n.raw, e.target.value); }}
                  onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                />
                <button type="button" className={w.linkBtn} onClick={() => removeAt(n.raw)}>
                  {t('cw.ct.remove')}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

// ===========================================================================
// Existing campaigns list row (unchanged behavior)
// ===========================================================================

function CampaignRow({ c, locale, sentLabel, repliedLabel, statusLabel }: {
  c: Campaign; locale: string; sentLabel: string; repliedLabel: string; statusLabel: string;
}) {
  // Mocked progress (no campaign-stats endpoint yet — see BACKEND_ENDPOINTS_NEEDED.md #7).
  const seed = c.id.length + (c.areas?.length ?? 0) * 7;
  const sent = 40 + (seed % 60);
  const replied = Math.round(sent * (0.45 + (seed % 20) / 100));
  const pct = Math.round((replied / sent) * 100);
  return (
    <div className={s.campaign}>
      <div className={s.campTop}>
        <span className={s.campName}>{c.name}</span>
        <Pill tone="ok">{statusLabel}</Pill>
      </div>
      <div className={s.campAreas}>
        {(c.areas ?? []).join(' · ') || '—'}
        {c.starts_at ? ` · ${formatDate(c.starts_at, locale)}` : ''}
      </div>
      <div className={s.progressTrack}>
        <div className={s.progressFill} style={{ width: `${pct}%` }} />
      </div>
      <div className={s.progressMeta}>
        <span className="tnum">{sent} {sentLabel}</span>
        <span className="tnum">{replied} {repliedLabel} ({pct}%)</span>
      </div>
    </div>
  );
}
