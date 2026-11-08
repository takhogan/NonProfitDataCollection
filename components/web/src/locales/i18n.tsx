import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { es, type MessageKey } from './es';
import { en } from './en';

export type Lang = 'es' | 'en';
const DICTS: Record<Lang, Record<MessageKey, string>> = { es, en };
export const LOCALES: Record<Lang, string> = { es: 'es-VE', en: 'en-US' };

export type Vars = Record<string, string | number>;

export function translate(lang: Lang, key: MessageKey, vars?: Vars): string {
  let msg = DICTS[lang][key] ?? es[key] ?? key;
  if (vars && typeof vars.count === 'number') {
    const plural = new Intl.PluralRules(LOCALES[lang]).select(vars.count);
    const alt = `${key}_${plural}` as MessageKey;
    if (DICTS[lang][alt]) msg = DICTS[lang][alt];
  }
  if (!vars) return msg;
  return msg.replace(/\{(\w+)\}/g, (_, k: string) =>
    k in vars ? (typeof vars[k] === 'number' ? new Intl.NumberFormat(LOCALES[lang]).format(vars[k]) : String(vars[k])) : `{${k}}`,
  );
}

interface I18n {
  lang: Lang;
  locale: string;
  setLang(l: Lang): void;
  t(key: MessageKey, vars?: Vars): string;
}

const I18nContext = createContext<I18n | null>(null);

/** Language lives in memory only (WEB-060); Spanish is the default (NFR-01). */
export function I18nProvider({ children, initial = 'es' }: { children: ReactNode; initial?: Lang }) {
  const [lang, setLang] = useState<Lang>(initial);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  const t = useCallback((key: MessageKey, vars?: Vars) => translate(lang, key, vars), [lang]);
  const value = useMemo(() => ({ lang, locale: LOCALES[lang], setLang, t }), [lang, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const c = useContext(I18nContext);
  if (!c) throw new Error('useI18n outside I18nProvider');
  return c;
}
