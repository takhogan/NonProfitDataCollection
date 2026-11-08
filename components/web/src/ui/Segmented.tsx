import type { ReactNode } from 'react';
import s from './Segmented.module.css';

export interface SegmentOption<T extends string> {
  value: T;
  label: ReactNode;
}

/** iOS/macOS segmented control for mutually-exclusive filters or presets. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: SegmentOption<T>[];
  value: T;
  onChange: (v: T) => void;
  ariaLabel?: string;
}) {
  return (
    <div className={s.wrap} role="tablist" aria-label={ariaLabel}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          className={`${s.seg} ${value === o.value ? s.on : ''}`}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
