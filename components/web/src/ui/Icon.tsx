import type { LucideIcon } from 'lucide-react';

/** Thin-stroke icon (SF Symbols feel). Use sparingly, only where it clarifies. */
export function Icon({ as: As, size = 18, strokeWidth = 1.5, className, style }: {
  as: LucideIcon;
  size?: number;
  strokeWidth?: number;
  className?: string;
  style?: React.CSSProperties;
}) {
  return <As size={size} strokeWidth={strokeWidth} className={className} style={style} aria-hidden />;
}
