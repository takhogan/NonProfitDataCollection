import { useEffect, useRef, useState } from 'react';
import { ArrowUp, X, MessageCircle } from 'lucide-react';
import { useAsk } from '../../api/product/queries';
import { useT } from '../i18n';
import { useLocalState } from '../shell/useLocalState';
import s from './AskBar.module.css';

const EXAMPLE_KEYS = ['dashboard.ask.ex1', 'dashboard.ask.ex2', 'dashboard.ask.ex3'] as const;

/** Persistent "Ask your data" composer docked at the bottom of the main area. */
export function AskBar() {
  const t = useT();
  const ask = useAsk();
  const [hidden, setHidden] = useLocalState<boolean>('metron.ask.hidden', false);
  const [q, setQ] = useState('');
  const [focused, setFocused] = useState(false);
  const [answer, setAnswer] = useState<{ question: string; text: string } | null>(null);
  const [exIndex, setExIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Rotate the placeholder example every few seconds (paused while typing).
  useEffect(() => {
    if (q) return;
    const id = setInterval(() => setExIndex((i) => (i + 1) % EXAMPLE_KEYS.length), 4000);
    return () => clearInterval(id);
  }, [q]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const question = q.trim();
    if (!question) return;
    try {
      const res = await ask.mutateAsync(question);
      setAnswer({ question, text: res.answer });
      setQ('');
    } catch {
      /* mutation error surfaced by disabling; keep input */
    }
  };

  if (hidden) {
    return (
      <button
        type="button"
        className={s.fab}
        onClick={() => {
          setHidden(false);
          setTimeout(() => inputRef.current?.focus(), 50);
        }}
        aria-label={t('dashboard.ask.title')}
        title={t('dashboard.ask.title')}
      >
        <MessageCircle size={20} strokeWidth={1.6} />
      </button>
    );
  }

  return (
    <div className={s.dock}>
      {answer && (
        <div className={s.answer} role="status">
          <div className={s.answerTop}>
            <span className={s.answerQ}>{answer.question}</span>
            <button type="button" className={s.answerClose} onClick={() => setAnswer(null)} aria-label={t('common.cancel')}>
              <X size={16} strokeWidth={1.75} />
            </button>
          </div>
          <p className={s.answerText}>{answer.text}</p>
        </div>
      )}

      <div className={`${s.barWrap} ${focused || q ? s.active : ''}`}>
        <span className={s.barBorder} aria-hidden />
        <form className={s.bar} onSubmit={submit}>
          <input
            ref={inputRef}
            className={s.input}
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder={t(EXAMPLE_KEYS[exIndex] ?? EXAMPLE_KEYS[0])}
            aria-label={t('dashboard.ask.title')}
          />
          <button type="button" className={s.hide} onClick={() => setHidden(true)}>
            {t('dashboard.ask.hide')}
          </button>
          <button type="submit" className={s.submit} disabled={ask.isPending || !q.trim()} aria-label={t('dashboard.ask.btn')}>
            <ArrowUp size={18} strokeWidth={2} />
          </button>
        </form>
      </div>
    </div>
  );
}
