import { useEffect, useState } from 'react';
import { Bot } from 'lucide-react';
import { useProductApi } from '../../api/product/context';
import { useCollectionTemplates, useMe, usePutBotConfig } from '../../api/product/queries';
import { useI18n } from '../../locales/i18n';
import { useT } from '../i18n';
import type { BotConfig } from '../../api/product';
import s from './Pages.module.css';

export default function BotEditorPage() {
  const t = useT();
  const { lang } = useI18n();
  const api = useProductApi();
  const me = useMe();
  const templates = useCollectionTemplates();
  const save = usePutBotConfig();

  const orgName = me.data?.memberships[0]?.organization_name ?? 'Metron';
  const [cfg, setCfg] = useState<BotConfig>({
    greeting: '',
    language_default: 'es',
    collection_template_id: 'power_water_outages',
    ask_consent: true,
    human_handoff_enabled: true,
  });
  const [loaded, setLoaded] = useState(false);

  // Load current bot config once.
  useEffect(() => {
    let active = true;
    // The contract has PUT but not GET for bot-config; start from a sensible default
    // and let the user edit. (See BACKEND_ENDPOINTS_NEEDED: a GET would be nice.)
    void api;
    if (active && !loaded) {
      setCfg((c) => ({ ...c, greeting: c.greeting || t('bot.defaultGreeting').replace('{org}', orgName), language_default: lang }));
      setLoaded(true);
    }
    return () => { active = false; };
  }, [api, loaded, orgName, lang, t]);

  const set = <K extends keyof BotConfig>(k: K, v: BotConfig[K]) => setCfg((c) => ({ ...c, [k]: v }));
  const template = templates.data?.find((tp) => tp.id === cfg.collection_template_id);

  return (
    <>
      <div className={s.head}>
        <h1>{t('bot.title')}</h1>
      </div>

      <div className={s.twoCol}>
        <div>
          <div className={s.field}>
            <label htmlFor="b-greeting">{t('bot.greeting')}</label>
            <textarea id="b-greeting" value={cfg.greeting ?? ''} onChange={(e) => set('greeting', e.target.value)} style={{ minHeight: 90 }} />
          </div>
          <div className={s.field}>
            <label htmlFor="b-lang">{t('bot.language')}</label>
            <select id="b-lang" value={cfg.language_default ?? 'es'} onChange={(e) => set('language_default', e.target.value)}>
              <option value="es">Español</option>
              <option value="en">English</option>
              <option value="ht">Kreyòl</option>
              <option value="pt">Português</option>
            </select>
          </div>
          <div className={s.field}>
            <label htmlFor="b-tpl">{t('bot.template')}</label>
            <select id="b-tpl" value={cfg.collection_template_id ?? ''} onChange={(e) => set('collection_template_id', e.target.value)}>
              {templates.data?.map((tp) => (
                <option key={tp.id} value={tp.id}>{tp.name}</option>
              ))}
            </select>
          </div>
          <div className={s.check}>
            <input id="b-consent" type="checkbox" checked={cfg.ask_consent ?? true} onChange={(e) => set('ask_consent', e.target.checked)} />
            <label htmlFor="b-consent" style={{ margin: 0 }}>{t('bot.askConsent')}</label>
          </div>
          <div className={s.check}>
            <input id="b-handoff" type="checkbox" checked={cfg.human_handoff_enabled ?? true} onChange={(e) => set('human_handoff_enabled', e.target.checked)} />
            <label htmlFor="b-handoff" style={{ margin: 0 }}>{t('bot.handoff')}</label>
          </div>
          <div className={s.saveBar}>
            <button type="button" disabled={save.isPending} onClick={() => save.mutate(cfg)}>
              {save.isPending ? t('common.saving') : t('common.save')}
            </button>
            {save.isSuccess && !save.isPending && <span className="muted" style={{ fontSize: '0.85rem' }}>{t('common.saved')}</span>}
          </div>
        </div>

        {/* WhatsApp-style preview */}
        <div>
          <p className="muted" style={{ marginTop: 0, marginBottom: '0.6rem', fontSize: '0.88rem' }}>{t('bot.previewHint')}</p>
          <div className={s.waPreview}>
            <div className={s.waHeader}>
              <span className={s.waAvatar} aria-hidden><Bot size={16} strokeWidth={1.75} color="#fff" /></span>
              {orgName}
            </div>
            {cfg.greeting && <div className={`${s.waBubble} ${s.waBot}`}>{cfg.greeting}</div>}
            {cfg.ask_consent && (
              <>
                <div className={`${s.waBubble} ${s.waBot}`}>{t('bot.consentLine')}</div>
                <div className={`${s.waBubble} ${s.waUser}`}>{t('bot.sampleYes')}</div>
              </>
            )}
            {(template?.questions ?? []).slice(0, 3).map((q, i) => (
              <div key={q.key}>
                <div className={`${s.waBubble} ${s.waBot}`}>{q.label}</div>
                {i === 0 && <div className={`${s.waBubble} ${s.waUser}`}>{t('bot.sampleAnswer')}</div>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
