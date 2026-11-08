import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { useProductApi } from '../../api/product/context';
import { useI18n } from '../../locales/i18n';
import { useT } from '../i18n';
import { errorText } from '../components/errors';
import { AuthFrame } from './AuthFrame';
import s from './Auth.module.css';
import { DEMO_EMAIL, DEMO_PASSWORD } from '../../api/product/mockData';

// Demo login shown on the page. The deployed build sets these (Dockerfile) to the
// seeded demo organization; local mock and dev keep the mock demo user.
const LOGIN_EMAIL = import.meta.env.VITE_DEMO_EMAIL || DEMO_EMAIL;
const LOGIN_PASSWORD = import.meta.env.VITE_DEMO_PASSWORD || DEMO_PASSWORD;

export default function LoginPage() {
  const t = useT();
  const { lang } = useI18n();
  const api = useProductApi();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [email, setEmail] = useState(LOGIN_EMAIL);
  const [password, setPassword] = useState(LOGIN_PASSWORD);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await api.login({ email, password });
      await qc.invalidateQueries();
      navigate('/app', { replace: true });
    } catch (ex) {
      setErr(errorText(ex, lang));
      setBusy(false);
    }
  };

  return (
    <AuthFrame>
      <h1 className={s.title}>{t('auth.loginTitle')}</h1>
      <form onSubmit={submit} noValidate>
        {err && <div className={s.err} role="alert">{err}</div>}
        <div className={s.field}>
          <label htmlFor="email">{t('auth.email')}</label>
          <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className={s.field}>
          <label htmlFor="password">{t('auth.password')}</label>
          <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        <button type="submit" className={s.submit} disabled={busy}>
          {busy ? t('common.loading') : t('auth.loginBtn')}
        </button>
      </form>
      <p className={s.demo}>{t('auth.demoHint')} {LOGIN_EMAIL} / {LOGIN_PASSWORD}</p>
      <p className={s.alt}>
        <Link to="/signup">{t('auth.toSignup')}</Link>
      </p>
    </AuthFrame>
  );
}
