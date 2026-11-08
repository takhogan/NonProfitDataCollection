import type { ReactNode } from 'react';
import { ChevronRight, Check } from 'lucide-react';
import { Link } from 'react-router';
import s from './list.module.css';

export function ListGroup({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={[s.group, className].filter(Boolean).join(' ')}>{children}</div>;
}

export function ListCaption({ children }: { children: ReactNode }) {
  return <p className={s.caption}>{children}</p>;
}

export function ListFootnote({ children }: { children: ReactNode }) {
  return <p className={s.footnote}>{children}</p>;
}

interface RowProps {
  title: ReactNode;
  sub?: ReactNode;
  value?: ReactNode;
  leading?: ReactNode;
  trailing?: ReactNode;
  /** show a selected check instead of chevron */
  selected?: boolean;
  chevron?: boolean;
  to?: string;
  onClick?: () => void;
}

export function Row({ title, sub, value, leading, trailing, selected, chevron, to, onClick }: RowProps) {
  const inner = (
    <>
      {leading != null && <span className={s.rowLeading}>{leading}</span>}
      <span className={s.rowBody}>
        <span className={s.rowTitle}>{title}</span>
        {sub != null && <span className={s.rowSub}>{sub}</span>}
      </span>
      {value != null && <span className={s.rowValue}>{value}</span>}
      {trailing}
      {selected && <Check size={18} strokeWidth={2} className={s.check} />}
      {chevron && !selected && <ChevronRight size={18} strokeWidth={1.75} className={s.chevron} />}
    </>
  );
  if (to) return <Link to={to} className={s.row}>{inner}</Link>;
  if (onClick) return <button type="button" className={s.row} onClick={onClick}>{inner}</button>;
  return <div className={s.row}>{inner}</div>;
}
