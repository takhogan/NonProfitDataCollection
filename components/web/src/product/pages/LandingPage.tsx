import { Link } from 'react-router';
import { Zap, Utensils, HeartHandshake } from 'lucide-react';
import { useI18n } from '../../locales/i18n';
import { useT } from '../i18n';
import { Tag } from '../../ui/kit';
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

      {/* Trust / safety */}
      <div className={s.trust}>
        <div className={s.trustInner}>
          <h2>{t('landing.trust.title')}</h2>
          <p>{t('landing.trust.body')}</p>
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
