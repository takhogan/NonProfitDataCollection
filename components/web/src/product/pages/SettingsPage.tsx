import { useEffect, useState } from 'react';
import {
  useChannels,
  useContacts,
  useDataProtection,
  useOrgProfile,
  usePutChannels,
  usePutDataProtection,
  usePutOrgProfile,
} from '../../api/product/queries';
import { useT, type ProductKey } from '../i18n';
import { Pill } from '../../ui/kit';
import { Segmented } from '../../ui/Segmented';
import { DataProtectionControls } from '../components/DataProtectionControls';
import type { ChannelsConfig, DataProtectionConfig, OrgProfile } from '../../api/product';
import s from './Pages.module.css';

type Tab = 'profile' | 'channels' | 'protection' | 'contacts';
const TABS: Tab[] = ['profile', 'channels', 'protection', 'contacts'];

export default function SettingsPage() {
  const t = useT();
  const [tab, setTab] = useState<Tab>('profile');

  const label = (tb: Tab): string => {
    if (tb === 'profile') return t('settings.profile');
    if (tb === 'channels') return t('settings.channels');
    if (tb === 'protection') return t('settings.protection');
    return t('reports.col.reporter') + 's';
  };

  return (
    <>
      <div className={s.head}>
        <h1>{t('settings.title')}</h1>
      </div>
      <div className={s.settingsNav}>
        <Segmented options={TABS.map((tb) => ({ value: tb, label: label(tb) }))} value={tab} onChange={setTab} ariaLabel={t('settings.title')} />
      </div>

      {tab === 'profile' && <ProfileTab />}
      {tab === 'channels' && <ChannelsTab />}
      {tab === 'protection' && <ProtectionTab />}
      {tab === 'contacts' && <ContactsTab />}
    </>
  );
}

function ProfileTab() {
  const t = useT();
  const q = useOrgProfile();
  const save = usePutOrgProfile();
  const [p, setP] = useState<OrgProfile | null>(null);
  useEffect(() => {
    if (q.data && !p) setP(q.data);
  }, [q.data, p]);
  if (!p) return <p className="muted">{t('common.loading')}</p>;

  return (
    <div style={{ maxWidth: 560 }}>
      <div className={s.field}>
        <label htmlFor="p-name">{t('onb.org.name')}</label>
        <input id="p-name" value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} />
      </div>
      <div className={s.field}>
        <label htmlFor="p-mission">{t('onb.org.mission')}</label>
        <textarea id="p-mission" value={p.mission ?? ''} onChange={(e) => setP({ ...p, mission: e.target.value })} />
      </div>
      <div className={s.field}>
        <label htmlFor="p-region">{t('onb.org.region')}</label>
        <input id="p-region" value={p.region ?? ''} onChange={(e) => setP({ ...p, region: e.target.value })} />
      </div>
      <div className={s.saveBar}>
        <button type="button" disabled={save.isPending} onClick={() => save.mutate(p)}>
          {save.isPending ? t('common.saving') : t('common.save')}
        </button>
        {save.isSuccess && !save.isPending && <span className="muted" style={{ fontSize: '0.85rem' }}>{t('common.saved')}</span>}
      </div>
    </div>
  );
}

function ChannelsTab() {
  const t = useT();
  const q = useChannels();
  const save = usePutChannels();
  const [cfg, setCfg] = useState<ChannelsConfig | null>(null);
  useEffect(() => {
    if (q.data && !cfg) setCfg(q.data);
  }, [q.data, cfg]);
  if (!cfg) return <p className="muted">{t('common.loading')}</p>;

  const update = (i: number, patch: Partial<ChannelsConfig['channels'][number]>) =>
    setCfg({ ...cfg, channels: cfg.channels.map((c, j) => (j === i ? { ...c, ...patch } : c)) });

  return (
    <div style={{ maxWidth: 760 }}>
      <div className={s.channelGroup}>
        {cfg.channels.map((c, i) => {
          const comingSoon = c.channel !== 'whatsapp';
          return (
            <div key={c.channel} className={s.channelRow}>
              <span className={s.channelName}>{t(`channel.${c.channel}` as ProductKey)}</span>
              <Pill tone={c.status === 'connected' ? 'ok' : c.status === 'pending' ? 'warn' : 'neutral'}>
                {t(`channel.status.${c.status}` as ProductKey)}
              </Pill>
              {comingSoon && <span className="muted" style={{ fontSize: '0.82rem' }}>{t('common.comingSoon')}</span>}
              <span className={s.channelSpacer} />
              <input
                type="text"
                value={c.identifier ?? ''}
                placeholder={t('channel.number')}
                onChange={(e) => update(i, { identifier: e.target.value })}
                style={{ maxWidth: 180 }}
              />
              <select value={c.mode ?? 'own_number'} onChange={(e) => update(i, { mode: e.target.value as 'shared_bot' | 'own_number' })}>
                <option value="shared_bot">{t('channel.mode.shared_bot')}</option>
                <option value="own_number">{t('channel.mode.own_number')}</option>
              </select>
              <button
                type="button"
                className="secondary"
                onClick={() => update(i, { status: c.status === 'connected' ? 'disconnected' : 'connected' })}
              >
                {c.status === 'connected' ? t('channel.status.disconnected') : t('channel.status.connected')}
              </button>
            </div>
          );
        })}
      </div>
      <div className={s.saveBar}>
        <button type="button" disabled={save.isPending} onClick={() => save.mutate(cfg)}>
          {save.isPending ? t('common.saving') : t('common.save')}
        </button>
        {save.isSuccess && !save.isPending && <span className="muted" style={{ fontSize: '0.85rem' }}>{t('common.saved')}</span>}
      </div>
    </div>
  );
}

function ProtectionTab() {
  const t = useT();
  const q = useDataProtection();
  const save = usePutDataProtection();
  const [dp, setDp] = useState<DataProtectionConfig | null>(null);
  useEffect(() => {
    if (q.data && !dp) setDp(q.data);
  }, [q.data, dp]);
  if (!dp) return <p className="muted">{t('common.loading')}</p>;

  return (
    <div style={{ maxWidth: 680 }}>
      <DataProtectionControls value={dp} onChange={setDp} />
      <div className={s.saveBar}>
        <button type="button" disabled={save.isPending} onClick={() => save.mutate(dp)}>
          {save.isPending ? t('common.saving') : t('common.save')}
        </button>
        {save.isSuccess && !save.isPending && <span className="muted" style={{ fontSize: '0.85rem' }}>{t('common.saved')}</span>}
      </div>
      <p className={s.sectionNote}>
        {t('dp.enforceNote')}
      </p>
    </div>
  );
}

function ContactsTab() {
  const t = useT();
  const contacts = useContacts();
  return (
    <div style={{ maxWidth: 760 }}>
      {contacts.isPending ? (
        <p className="muted">{t('common.loading')}</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className={s.contactsTable}>
            <thead>
              <tr>
                <th>{t('onb.org.name')}</th>
                <th>Tel</th>
                <th>{t('reports.col.area')}</th>
                <th>Consent</th>
              </tr>
            </thead>
            <tbody>
              {contacts.data?.map((c) => (
                <tr key={c.id}>
                  <td>{c.name ?? <span className="muted">{t('reports.nameHidden')}</span>}</td>
                  <td className="tnum">{c.phone ?? '—'}</td>
                  <td>{c.area ?? '—'}</td>
                  <td>
                    <Pill tone={c.consent_status === 'granted' ? 'ok' : c.consent_status === 'declined' ? 'danger' : 'warn'}>
                      {t(`consent.${c.consent_status}` as ProductKey)}
                    </Pill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
