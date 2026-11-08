import { useEffect, useMemo, useState } from 'react';
import { Check } from 'lucide-react';
import { Link, useNavigate } from 'react-router';
import { useI18n } from '../../locales/i18n';
import { useProductApi } from '../../api/product/context';
import {
  useCollectionTemplates,
  useDashboardTemplates,
  useOrgProfile,
  useRecommendedCollection,
} from '../../api/product/queries';
import { useT, type ProductKey } from '../i18n';
import { DataProtectionControls } from '../components/DataProtectionControls';
import type {
  DashboardTemplate,
  DataProtectionConfig,
  OrgProfile,
  TemplateQuestion,
} from '../../api/product';
import s from './Onboarding.module.css';

type StepId = 'org' | 'goal' | 'dashboard' | 'protection' | 'review';
const STEPS: StepId[] = ['org', 'goal', 'dashboard', 'protection', 'review'];
const ORG_TYPES: OrgProfile['type'][] = ['NGO', 'NPO', 'community', 'foundation', 'other'];

export default function OnboardingPage() {
  const t = useT();
  const { lang } = useI18n();
  const api = useProductApi();
  const navigate = useNavigate();

  const profileQ = useOrgProfile();
  const collectionsQ = useCollectionTemplates();
  const recommendedQ = useRecommendedCollection();
  const dashboardsQ = useDashboardTemplates();

  const [step, setStep] = useState<StepId>('org');
  const [profile, setProfile] = useState<OrgProfile>({ name: '', type: 'community', mission: '', region: '', languages: [], population_served: '', team_size: null });
  const [collectionId, setCollectionId] = useState<string | null>(null);
  const [questions, setQuestions] = useState<TemplateQuestion[]>([]);
  const [dashboardId, setDashboardId] = useState<string | null>(null);
  const [widgets, setWidgets] = useState<string[]>([]);
  const [protection, setProtection] = useState<DataProtectionConfig>({
    preset: 'standard', store_names: true, location_precision: 'precise', raw_message_retention_days: 90,
    mask_phone_numbers: false, redact_exports: false, individual_records_roles: ['org_admin', 'coordinator'], audit_log_enabled: true,
    hide_individual_records: false,
  });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Seed from the server once loaded (save-as-you-go: start from current profile).
  useEffect(() => {
    if (profileQ.data) setProfile((p) => (p.name ? p : profileQ.data));
  }, [profileQ.data]);

  // Pick recommended collection by default.
  const recommendedCollectionId = recommendedQ.data?.recommended_collection_ids?.[0];
  useEffect(() => {
    if (collectionId || !collectionsQ.data) return;
    const pick = recommendedCollectionId ?? collectionsQ.data[0]?.id ?? null;
    setCollectionId(pick);
  }, [collectionsQ.data, recommendedCollectionId, collectionId]);

  // Load the chosen collection's questions for inline editing.
  const selectedCollection = collectionsQ.data?.find((c) => c.id === collectionId);
  useEffect(() => {
    if (selectedCollection) setQuestions(selectedCollection.questions ?? []);
  }, [selectedCollection]);

  // Pick recommended dashboard by default.
  const recommendedDashboard = dashboardsQ.data?.find((d) => d.recommended) ?? dashboardsQ.data?.[0];
  useEffect(() => {
    if (dashboardId || !recommendedDashboard) return;
    setDashboardId(recommendedDashboard.id);
    setWidgets(recommendedDashboard.widgets?.map((w) => w.key) ?? []);
  }, [recommendedDashboard, dashboardId]);

  const idx = STEPS.indexOf(step);
  const next = () => setStep(STEPS[Math.min(STEPS.length - 1, idx + 1)]!);
  const back = () => setStep(STEPS[Math.max(0, idx - 1)]!);

  // Save-as-you-go: persist the step we're leaving, then advance.
  const saveAndNext = async () => {
    setErr(null);
    try {
      if (step === 'org') {
        if (!profile.name.trim()) {
          setErr(t('onb.err.name'));
          return;
        }
        await api.putOrgProfile(profile);
      } else if (step === 'goal' && collectionId) {
        await api.putBotConfig({ greeting: '', language_default: lang, collection_template_id: collectionId, ask_consent: true, human_handoff_enabled: true });
      } else if (step === 'dashboard' && dashboardId) {
        await api.putDashboardConfig({ template_id: dashboardId, widgets });
      } else if (step === 'protection') {
        await api.putDataProtection(protection);
      }
      next();
    } catch {
      setErr(t('error.generic'));
    }
  };

  const launch = async () => {
    setBusy(true);
    setErr(null);
    try {
      // Persist everything (idempotent) then enter the app.
      await api.putOrgProfile(profile);
      if (collectionId) await api.putBotConfig({ greeting: '', language_default: lang, collection_template_id: collectionId, ask_consent: true, human_handoff_enabled: true });
      if (dashboardId) await api.putDashboardConfig({ template_id: dashboardId, widgets });
      await api.putDataProtection(protection);
      navigate('/app', { replace: true });
    } catch {
      setErr(t('error.generic'));
      setBusy(false);
    }
  };

  return (
    <div className={s.page}>
      <div className={s.bar}>
        <Link to="/" className={s.brand}>
          <span className={s.brandDot} aria-hidden />
          {t('brand.name')}
        </Link>
      </div>
      <div className={s.wrap}>
        <p className={s.stepLabel}>
          {t(`onb.step.${step}` as ProductKey)} · {idx + 1}/{STEPS.length}
        </p>
        <div className={s.steps} aria-hidden>
          {STEPS.map((st, i) => (
            <span key={st} className={`${s.stepDot} ${i === idx ? s.stepDotActive : i < idx ? s.stepDotDone : ''}`} />
          ))}
        </div>

        <div className={s.card}>
          {err && <div className={s.err} role="alert">{err}</div>}

          {step === 'org' && (
            <>
              <h1 className={s.title}>{t('onb.org.title')}</h1>
              <p className={s.sub}>{t('onb.org.sub')}</p>
              <div className={s.field}>
                <label htmlFor="o-name">{t('onb.org.name')}</label>
                <input id="o-name" value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
              </div>
              <div className={s.row2}>
                <div className={s.field}>
                  <label htmlFor="o-type">{t('onb.org.type')}</label>
                  <select id="o-type" value={profile.type} onChange={(e) => setProfile({ ...profile, type: e.target.value as OrgProfile['type'] })}>
                    {ORG_TYPES.map((o) => (
                      <option key={o} value={o}>{t(`orgType.${o}`)}</option>
                    ))}
                  </select>
                </div>
                <div className={s.field}>
                  <label htmlFor="o-region">{t('onb.org.region')}</label>
                  <input id="o-region" value={profile.region ?? ''} onChange={(e) => setProfile({ ...profile, region: e.target.value })} />
                </div>
              </div>
              <div className={s.field}>
                <label htmlFor="o-mission">{t('onb.org.mission')}</label>
                <textarea id="o-mission" value={profile.mission ?? ''} onChange={(e) => setProfile({ ...profile, mission: e.target.value })} />
              </div>
              <div className={s.row2}>
                <div className={s.field}>
                  <label htmlFor="o-pop">{t('onb.org.population')}</label>
                  <input id="o-pop" value={profile.population_served ?? ''} onChange={(e) => setProfile({ ...profile, population_served: e.target.value })} />
                </div>
                <div className={s.field}>
                  <label htmlFor="o-team">{t('onb.org.team')}</label>
                  <input id="o-team" type="number" min={1} value={profile.team_size ?? ''} onChange={(e) => setProfile({ ...profile, team_size: e.target.value ? Number(e.target.value) : null })} />
                </div>
              </div>
              <LanguagePicker value={profile.languages ?? []} onChange={(languages) => setProfile({ ...profile, languages })} label={t('onb.org.languages')} />
            </>
          )}

          {step === 'goal' && (
            <>
              <h1 className={s.title}>{t('onb.goal.title')}</h1>
              <p className={s.sub}>{t('onb.goal.sub')}</p>
              <div className={s.optionGroup}>
                {collectionsQ.data?.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    className={`${s.option} ${collectionId === c.id ? s.optionOn : ''}`}
                    onClick={() => setCollectionId(c.id)}
                    aria-pressed={collectionId === c.id}
                  >
                    <div className={s.optionBody}>
                      <h3>
                        {c.name}
                        {c.id === recommendedCollectionId && <span className={s.recTag}>{t('common.recommended')}</span>}
                      </h3>
                      <p>{c.description}</p>
                    </div>
                    {collectionId === c.id && <Check size={19} strokeWidth={2} className={s.optionCheck} />}
                  </button>
                ))}
              </div>

              {questions.length > 0 && (
                <div className={s.qList}>
                  <p className={s.qCaption}>{t('onb.goal.questions')}</p>
                  {questions.map((q, i) => (
                    <div key={q.key} className={s.qRow}>
                      <input
                        type="text"
                        value={q.label}
                        onChange={(e) => setQuestions((qs) => qs.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))}
                        aria-label={`${t('onb.goal.questions')} ${i + 1}`}
                      />
                      <span className={s.qType}>{q.field_type}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {step === 'dashboard' && (
            <>
              <h1 className={s.title}>{t('onb.dash.title')}</h1>
              <p className={s.sub}>{t('onb.dash.sub')}</p>
              <div className={s.optionGroup}>
                {dashboardsQ.data?.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    className={`${s.option} ${dashboardId === d.id ? s.optionOn : ''}`}
                    onClick={() => {
                      setDashboardId(d.id);
                      setWidgets(d.widgets?.map((w) => w.key) ?? []);
                    }}
                    aria-pressed={dashboardId === d.id}
                  >
                    <DashboardPreview tpl={d} />
                    <div className={s.optionBody}>
                      <h3>
                        {d.name}
                        {d.recommended && <span className={s.recTag}>{t('common.recommended')}</span>}
                      </h3>
                      <p>{d.description}</p>
                    </div>
                    {dashboardId === d.id && <Check size={19} strokeWidth={2} className={s.optionCheck} />}
                  </button>
                ))}
              </div>

              {dashboardId && (
                <>
                  <p className={s.qCaption} style={{ marginTop: '1.5rem' }}>{t('onb.dash.widgets')}</p>
                  <div className={s.widgets}>
                    {allWidgets(dashboardsQ.data ?? []).map((w) => (
                      <button
                        key={w}
                        type="button"
                        className={`${s.chip} ${widgets.includes(w) ? s.chipOn : ''}`}
                        onClick={() => setWidgets((ws) => (ws.includes(w) ? ws.filter((x) => x !== w) : [...ws, w]))}
                        aria-pressed={widgets.includes(w)}
                      >
                        {t(`widget.${w}` as ProductKey)}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </>
          )}

          {step === 'protection' && (
            <>
              <h1 className={s.title}>{t('dp.title')}</h1>
              <DataProtectionControls value={protection} onChange={setProtection} />
            </>
          )}

          {step === 'review' && (
            <>
              <h1 className={s.title}>{t('onb.review.title')}</h1>
              <p className={s.sub}>{t('onb.review.sub')}</p>
              <div className={s.reviewGroup}>
                <div className={s.reviewRow}>
                  <span>{t('onb.review.org')}</span>
                  <span>{profile.name} · {t(`orgType.${profile.type}`)}{profile.region ? ` · ${profile.region}` : ''}</span>
                </div>
                <div className={s.reviewRow}>
                  <span>{t('onb.review.goal')}</span>
                  <span>{selectedCollection?.name ?? '—'}</span>
                </div>
                <div className={s.reviewRow}>
                  <span>{t('onb.review.dashboard')}</span>
                  <span>{dashboardsQ.data?.find((d) => d.id === dashboardId)?.name ?? '—'} · {widgets.length} widgets</span>
                </div>
                <div className={s.reviewRow}>
                  <span>{t('onb.review.protection')}</span>
                  <span>{t(`dp.preset.${protection.preset}` as ProductKey)}</span>
                </div>
              </div>
            </>
          )}

          <div className={s.nav}>
            <button type="button" className="secondary" onClick={back} disabled={idx === 0 || busy}>
              {t('common.back')}
            </button>
            {step === 'review' ? (
              <button type="button" onClick={launch} disabled={busy}>
                {busy ? t('onb.launching') : t('onb.launch')}
              </button>
            ) : (
              <button type="button" onClick={saveAndNext} disabled={busy}>
                {t('common.next')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function allWidgets(templates: DashboardTemplate[]): string[] {
  const set = new Set<string>();
  templates.forEach((t) => t.widgets?.forEach((w) => set.add(w.key)));
  return [...set];
}

function DashboardPreview({ tpl }: { tpl: DashboardTemplate }) {
  const keys = tpl.widgets?.map((w) => w.type) ?? [];
  return (
    <div className={s.previewMini} aria-hidden>
      {keys.includes('metric') && (
        <div className={s.pvRow}>
          <span className={s.pvCell} />
          <span className={s.pvCell} />
          <span className={s.pvCell} />
        </div>
      )}
      {keys.includes('map') && <span className={s.pvBig} />}
      {keys.includes('chart') && <span className={s.pvBig} />}
      {keys.includes('list') && (
        <>
          <span className={s.pvBar} style={{ width: '80%' }} />
          <span className={s.pvBar} style={{ width: '60%' }} />
        </>
      )}
      {keys.includes('feed') && (
        <>
          <span className={s.pvFeed} />
          <span className={s.pvFeed} />
        </>
      )}
    </div>
  );
}

function LanguagePicker({ value, onChange, label }: { value: string[]; onChange: (v: string[]) => void; label: string }) {
  const OPTIONS = useMemo(() => [
    { code: 'es', label: 'Español' },
    { code: 'en', label: 'English' },
    { code: 'ht', label: 'Kreyòl' },
    { code: 'pt', label: 'Português' },
    { code: 'fr', label: 'Français' },
  ], []);
  const toggle = (code: string) => onChange(value.includes(code) ? value.filter((c) => c !== code) : [...value, code]);
  return (
    <div className={s.field}>
      <label>{label}</label>
      <div className={s.chips}>
        {OPTIONS.map((o) => (
          <button key={o.code} type="button" className={`${s.chip} ${value.includes(o.code) ? s.chipOn : ''}`} onClick={() => toggle(o.code)} aria-pressed={value.includes(o.code)}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
