import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { useProductApi } from '../../api/product/context';
import { useI18n } from '../../locales/i18n';
import { useT } from '../i18n';
import { errorText } from '../components/errors';
import { AuthFrame } from './AuthFrame';
import type { SignupRequest } from '../../api/product';
import s from './Auth.module.css';

const ORG_TYPES: SignupRequest['org_type'][] = ['NGO', 'NPO', 'community', 'foundation', 'other'];

export default function SignupPage() {
  const t = useT();
  const { lang } = useI18n();
  const api = useProductApi();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [form, setForm] = useState<SignupRequest>({ email: '', password: '', display_name: '', org_name: '', org_type: 'community' });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof SignupRequest>(k: K, v: SignupRequest[K]) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await api.signup(form);
      await qc.invalidateQueries();
      // New org → go to onboarding.
      navigate('/onboarding', { replace: true });
    } catch (ex) {
      setErr(errorText(ex, lang));
      setBusy(false);
    }
  };

  return (
    <AuthFrame>
      <h1 className={s.title}>{t('auth.signupTitle')}</h1>
      <form onSubmit={submit} noValidate>
        {err && <div className={s.err} role="alert">{err}</div>}
        <div className={s.field}>
          <label htmlFor="org_name">{t('auth.orgName')}</label>
          <input id="org_name" value={form.org_name} onChange={(e) => set('org_name', e.target.value)} required />
        </div>
        <div className={s.field}>
          <label htmlFor="org_type">{t('auth.orgType')}</label>
          <select id="org_type" value={form.org_type} onChange={(e) => set('org_type', e.target.value as SignupRequest['org_type'])}>
            {ORG_TYPES.map((o) => (
              <option key={o} value={o}>
                {t(`orgType.${o}`)}
              </option>
            ))}
          </select>
        </div>
        <div className={s.field}>
          <label htmlFor="display_name">{t('auth.displayName')}</label>
          <input id="display_name" value={form.display_name} onChange={(e) => set('display_name', e.target.value)} autoComplete="name" />
        </div>
        <div className={s.field}>
          <label htmlFor="email">{t('auth.email')}</label>
          <input id="email" type="email" autoComplete="username" value={form.email} onChange={(e) => set('email', e.target.value)} required />
        </div>
        <div className={s.field}>
          <label htmlFor="password">{t('auth.password')}</label>
          <input id="password" type="password" autoComplete="new-password" value={form.password} onChange={(e) => set('password', e.target.value)} required />
        </div>
        <button type="submit" className={s.submit} disabled={busy}>
          {busy ? t('common.loading') : t('auth.signupBtn')}
        </button>
      </form>
      <p className={s.alt}>
        <Link to="/login">{t('auth.toLogin')}</Link>
      </p>
    </AuthFrame>
  );
}
