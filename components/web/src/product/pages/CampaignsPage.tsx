import { useState } from 'react';
import { useI18n } from '../../locales/i18n';
import { formatDate } from '../../locales/format';
import { useCampaigns, useCollectionTemplates, useCreateCampaign } from '../../api/product/queries';
import { useT } from '../i18n';
import { Pill } from '../../ui/kit';
import type { Campaign } from '../../api/product';
import s from './Pages.module.css';

export default function CampaignsPage() {
  const t = useT();
  const campaigns = useCampaigns();
  const templates = useCollectionTemplates();
  const create = useCreateCampaign();
  const { locale } = useI18n();

  const [name, setName] = useState('');
  const [templateId, setTemplateId] = useState('');
  const [areas, setAreas] = useState('');
  const [mode, setMode] = useState<'proactive' | 'wait'>('proactive');

  const defaultTemplate = templateId || templates.data?.[0]?.id || 'power_water_outages';

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    await create.mutateAsync({
      name: name.trim(),
      collection_template_id: defaultTemplate,
      areas: areas.split(',').map((a) => a.trim()).filter(Boolean),
      starts_at: null,
      ends_at: null,
    });
    setName('');
    setAreas('');
  };

  return (
    <>
      <div className={s.head}>
        <h1>{t('campaigns.title')}</h1>
      </div>

      <div className={s.twoCol}>
        <div>
          {campaigns.isPending ? (
            <p className="muted">{t('common.loading')}</p>
          ) : !campaigns.data || campaigns.data.length === 0 ? (
            <p className="muted">{t('campaigns.empty')}</p>
          ) : (
            <div className={s.campaignGroup}>
              {campaigns.data.map((c) => (
                <CampaignRow key={c.id} c={c} locale={locale} sentLabel={t('campaigns.sent')} repliedLabel={t('campaigns.replied')} statusLabel={t('campaigns.status.active')} />
              ))}
            </div>
          )}
        </div>

        <div>
          <h2 className={s.panelTitle}>{t('campaigns.new')}</h2>
          <form onSubmit={submit}>
            <div className={s.field}>
              <label htmlFor="c-name">{t('campaigns.name')}</label>
              <input id="c-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className={s.field}>
              <label htmlFor="c-tpl">{t('campaigns.template')}</label>
              <select id="c-tpl" value={defaultTemplate} onChange={(e) => setTemplateId(e.target.value)}>
                {templates.data?.map((tpl) => (
                  <option key={tpl.id} value={tpl.id}>{tpl.name}</option>
                ))}
              </select>
            </div>
            <div className={s.field}>
              <label htmlFor="c-areas">{t('campaigns.areas')}</label>
              <input id="c-areas" value={areas} onChange={(e) => setAreas(e.target.value)} placeholder="Little Haiti, Liberty City" />
            </div>
            <div className={s.check}>
              <input id="c-proactive" type="radio" checked={mode === 'proactive'} onChange={() => setMode('proactive')} />
              <label htmlFor="c-proactive" style={{ margin: 0 }}>{t('campaigns.proactive')}</label>
            </div>
            <div className={s.check}>
              <input id="c-wait" type="radio" checked={mode === 'wait'} onChange={() => setMode('wait')} />
              <label htmlFor="c-wait" style={{ margin: 0 }}>{t('campaigns.wait')}</label>
            </div>
            <button type="submit" disabled={create.isPending || !name.trim()}>
              {create.isPending ? t('common.saving') : t('campaigns.create')}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}

function CampaignRow({ c, locale, sentLabel, repliedLabel, statusLabel }: { c: Campaign; locale: string; sentLabel: string; repliedLabel: string; statusLabel: string }) {
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
