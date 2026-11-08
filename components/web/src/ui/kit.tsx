import type { CSSProperties, ReactNode } from 'react';
import k from './kit.module.css';

export { k as kitStyles };

type Tone = 'neutral' | 'accent' | 'ok' | 'warn' | 'danger';

export function Card({ children, className, style, pad = true }: { children: ReactNode; className?: string; style?: CSSProperties; pad?: boolean }) {
  return <div className={[pad ? k.card : `${k.card} ${k.cardPad0}`, className].filter(Boolean).join(' ')} style={style}>{children}</div>;
}

export function Pill({ children, tone = 'neutral' }: { children: ReactNode; tone?: Tone }) {
  return <span className={`${k.pill} ${k[tone]}`}>{children}</span>;
}

export function Tag({ children }: { children: ReactNode }) {
  return <span className={k.tag}>{children}</span>;
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className={k.eyebrow}>{children}</p>;
}

export function Lead({ children }: { children: ReactNode }) {
  return <p className={k.lead}>{children}</p>;
}

export function Stat({ value, label, hint, tone }: { value: ReactNode; label: ReactNode; hint?: ReactNode; tone?: Tone }) {
  const color = tone && tone !== 'neutral' ? `var(--${tone === 'danger' ? 'danger' : tone === 'warn' ? 'warn' : tone === 'ok' ? 'ok' : 'accent'})` : undefined;
  return (
    <div className={k.stat}>
      <span className={k.statValue} style={{ color }}>{value}</span>
      <span className={k.statLabel}>{label}</span>
      {hint != null && <span className={k.statHint}>{hint}</span>}
    </div>
  );
}

export function LiveDot({ label }: { label: string }) {
  return (
    <span className={k.live}>
      <span className={k.dot} aria-hidden />
      {label}
    </span>
  );
}

export function Grid({ cols = 3, children, style }: { cols?: 2 | 3 | 4; children: ReactNode; style?: CSSProperties }) {
  const cls = cols === 2 ? k.cols2 : cols === 4 ? k.cols4 : k.cols3;
  return <div className={`${k.grid} ${cls}`} style={style}>{children}</div>;
}

export function Stack({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <div className={k.stack} style={style}>{children}</div>;
}

export function Row({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <div className={k.row} style={style}>{children}</div>;
}

export function Spread({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <div className={k.spread} style={style}>{children}</div>;
}
