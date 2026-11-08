import { Link } from 'react-router';
import { Zap, Utensils, HeartHandshake, MessageSquareText, MapPinned, UserRound, MapPin, Phone, SlidersHorizontal } from 'lucide-react';
import { useI18n } from '../../locales/i18n';
import { useT, type ProductKey } from '../i18n';
import { Tag, Pill, Stat } from '../../ui/kit';
import { AREAS, FEED_SEED } from '../../api/product/mockData';
import { UrgentPill } from '../components/bits';
import s from './Landing.module.css';

export default function LandingPage() {
  const t = useT();
  const { lang, setLang } = useI18n();

  const useCases = [
    { icon: Zap, title: t('landing.use.outages'), body: t('landing.use.outagesBody') },
    { icon: Utensils, title: t('landing.use.food'), body: t('landing.use.foodBody') },
    { icon: HeartHandshake, title: t('landing.use.elderly'), body: t('landing.use.elderlyBody') },
  ];
  const steps = [
    { title: t('landing.step.configure'), body: t('landing.step.configureBody') },
    { title: t('landing.step.collect'), body: t('landing.step.collectBody') },
    { title: t('landing.step.see'), body: t('landing.step.seeBody') },
  ];
  const audiences = [
    {
      icon: MessageSquareText,
      title: t('landing.who.collect'),
      lead: t('landing.who.collectLead'),
      points: [t('landing.who.collect1'), t('landing.who.collect2'), t('landing.who.collect3')],
    },
    {
      icon: MapPinned,
      title: t('landing.who.act'),
      lead: t('landing.who.actLead'),
      points: [t('landing.who.act1'), t('landing.who.act2'), t('landing.who.act3')],
    },
  ];
  const privacy = [
    { icon: UserRound, title: t('landing.trust.anon'), body: t('landing.trust.anonBody') },
    { icon: MapPin, title: t('landing.trust.address'), body: t('landing.trust.addressBody') },
    { icon: Phone, title: t('landing.trust.phone'), body: t('landing.trust.phoneBody') },
    { icon: SlidersHorizontal, title: t('landing.trust.profile'), body: t('landing.trust.profileBody') },
  ];

  return (
    <div className={s.page}>
      <div className={s.hero}>
        <div className={s.bar}>
          <span className={s.brand}>{t('brand.name')}</span>
          <div className={s.barActions}>
            <button type="button" className="secondary" onClick={() => setLang(lang === 'es' ? 'en' : 'es')}>
              {lang === 'es' ? 'EN' : 'ES'}
            </button>
            <Link to="/login" className={s.navLogin}>
              {t('landing.login')}
            </Link>
          </div>
        </div>
        <div className={s.heroInner}>
          <div className={s.heroCopy}>
            <h1 className={s.h1}>{t('brand.tagline')}</h1>
            <p className={s.heroLead}>
              {lang === 'es'
                ? 'Metron le da a su organización un agente que conversa por WhatsApp con las personas que atiende y convierte cada respuesta en datos y un panel en vivo.'
                : 'Metron gives your organization an agent that talks with the people you serve over WhatsApp and turns every answer into structured data and a live dashboard.'}
            </p>
            <div className={s.heroCtas}>
              <Link to="/signup" className={`${s.btnLg} ${s.btnPrimary}`}>
                {t('landing.cta')}
              </Link>
              <Link to="/login" className={`${s.btnLg} ${s.btnText}`}>
                {t('landing.login')}
              </Link>
            </div>
          </div>
          <ChatVisual turnsLabel={t('landing.chat.turns')} />
        </div>
      </div>

      {/* Use cases */}
      <section className={s.section}>
        <h2 className={s.sectionTitle}>{lang === 'es' ? 'Para muchos tipos de trabajo' : 'For many kinds of work'}</h2>
        <div className={s.cards3}>
          {useCases.map((u) => {
            const I = u.icon;
            return (
              <div key={u.title} className={s.useCard}>
                <I size={22} strokeWidth={1.5} className={s.useIcon} aria-hidden />
                <h3>{u.title}</h3>
                <p>{u.body}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* How it works */}
      <section className={s.section} style={{ paddingTop: 0 }}>
        <h2 className={s.sectionTitle}>{t('landing.how')}</h2>
        <div className={s.howStrip}>
          {steps.map((step, i) => (
            <div key={step.title} className={s.howStep}>
              <span className={s.howNum}>{i + 1}</span>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Who it's for */}
      <section className={s.section} style={{ paddingTop: 0 }}>
        <h2 className={s.sectionTitle}>{t('landing.who.title')}</h2>
        <div className={s.cards2}>
          {audiences.map((a) => {
            const I = a.icon;
            return (
              <div key={a.title} className={s.audience}>
                <I size={22} strokeWidth={1.5} className={s.useIcon} aria-hidden />
                <h3>{a.title}</h3>
                <p className={s.audienceLead}>{a.lead}</p>
                <ul className={s.points}>
                  {a.points.map((pt) => (
                    <li key={pt}>{pt}</li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
        <p className={s.sharedNote}>{t('landing.who.shared')}</p>
      </section>

      {/* Dashboard preview (synthetic data) */}
      <section className={s.section} style={{ paddingTop: 0 }}>
        <DashboardPreview />
      </section>

      {/* Trust / safety */}
      <div className={s.trust}>
        <div className={s.trustInner}>
          <h2>{t('landing.trust.title')}</h2>
          <p>{t('landing.trust.body')}</p>
          <div className={s.trustGrid}>
            {privacy.map((p) => {
              const I = p.icon;
              return (
                <div key={p.title} className={s.trustPoint}>
                  <I size={20} strokeWidth={1.5} className={s.useIcon} aria-hidden />
                  <h3>{p.title}</h3>
                  <p>{p.body}</p>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Final CTA */}
      <div className={s.ctaFinal}>
        <h2>{lang === 'es' ? 'Empiece hoy' : 'Start today'}</h2>
        <p className={s.ctaSub}>
          {lang === 'es' ? 'Cree su organización en unos minutos.' : 'Create your organization in a few minutes.'}
        </p>
        <Link to="/signup" className={`${s.btnLg} ${s.btnPrimary}`}>
          {t('landing.cta')}
        </Link>
      </div>

      <footer className={s.footer}>Metron · {lang === 'es' ? 'Proyecto de hackathon' : 'Hackathon project'}</footer>
    </div>
  );
}

function ChatVisual({ turnsLabel }: { turnsLabel: string }) {
  const t = useT();
  return (
    <div className={s.visual}>
      <div className={s.chat}>
        <div className={`${s.bubble} ${s.fromReporter}`}>{t('landing.chat.msg1')}</div>
        <div className={`${s.bubble} ${s.fromBot}`}>{t('landing.chat.msg2')}</div>
        <div className={`${s.bubble} ${s.fromReporter}`}>{t('landing.chat.msg3')}</div>
      </div>
      <p className={s.turns}>{turnsLabel}</p>
      <div className={s.resultTags}>
        <Tag>{t('landing.chat.tag1')}</Tag>
        <Tag>{t('landing.chat.tag2')}</Tag>
        <Tag>{t('landing.chat.tag3')}</Tag>
        <Tag>{t('landing.chat.tag4')}</Tag>
      </div>
    </div>
  );
}

const NEED_KEYS: Partial<Record<string, ProductKey>> = {
  no_power: 'landing.demo.need.no_power',
  no_water: 'landing.demo.need.no_water',
  power_restored: 'landing.demo.need.power_restored',
};

/** Static, non-interactive dashboard preview built from the mock client's synthetic data. */
function DashboardPreview() {
  const t = useT();
  const totals = AREAS.reduce(
    (acc, a) => ({ reports: acc.reports + a.reports, urgent: acc.urgent + a.urgent }),
    { reports: 0, urgent: 0 },
  );
  const max = Math.max(...AREAS.map((a) => a.reports));
  const recent = [...FEED_SEED].reverse();

  return (
    <div className={s.demo} aria-label={t('landing.demo.eyebrow')}>
      <div className={s.demoHead}>
        <div>
          <p className={s.demoEyebrow}>{t('landing.demo.eyebrow')}</p>
          <h2 className={s.demoTitle}>{t('landing.demo.title')}</h2>
          <p className={s.demoOrg}>{t('landing.demo.org')}</p>
        </div>
        <Pill tone="warn">{t('landing.demo.sample')}</Pill>
      </div>

      <div className={s.demoStats}>
        <Stat value={totals.reports} label={t('landing.demo.reports')} />
        <Stat value={AREAS.length} label={t('landing.demo.areas')} />
        <Stat value={totals.urgent} label={t('landing.demo.urgent')} tone="danger" />
      </div>

      <div className={s.demoBody}>
        <div>
          <h3 className={s.demoH3}>{t('landing.demo.byArea')}</h3>
          <div className={s.legend} aria-hidden>
            <span><i className={s.swPower} /> {t('landing.demo.noPower')}</span>
            <span><i className={s.swWater} /> {t('landing.demo.noWater')}</span>
          </div>
          {AREAS.map((a) => (
            <div key={a.area} className={s.areaRow}>
              <div className={s.areaTop}>
                <span>{a.area}</span>
                <span className={`${s.areaCount} tnum`}>{a.reports}</span>
              </div>
              <div className={s.areaTrack} style={{ width: `${(a.reports / max) * 100}%` }} aria-hidden>
                <span className={s.swPower} style={{ width: `${(a.without_power / a.reports) * 100}%` }} />
                <span className={s.swWater} style={{ width: `${(a.without_water / a.reports) * 100}%` }} />
              </div>
              <div className={`${s.areaMeta} tnum`}>
                {a.without_power} {t('landing.demo.noPower')} · {a.without_water} {t('landing.demo.noWater')}
              </div>
            </div>
          ))}
        </div>

        <div>
          <h3 className={s.demoH3}>{t('landing.demo.recent')}</h3>
          <table className={s.demoTable}>
            <thead>
              <tr>
                <th>{t('landing.demo.colArea')}</th>
                <th>{t('landing.demo.colNeed')}</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((f) => {
                const need = (f.tags ?? []).map((tag) => NEED_KEYS[tag]).find(Boolean);
                return (
                  <tr key={f.id}>
                    <td>
                      <span className={s.cellArea}>{f.area}</span>
                      <span className={s.cellPreview}>{f.preview}</span>
                    </td>
                    <td>
                      <span className={s.cellNeed}>{t(need ?? 'landing.demo.need.other')}</span>
                      {(f.tags ?? []).includes('urgent') && <UrgentPill />}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      <p className={s.demoFoot}>{t('landing.demo.footnote')}</p>
    </div>
  );
}
