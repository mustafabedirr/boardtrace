import type { ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
const statuses = {
  ready: 'text-success border-success-border bg-success-surface',
  capturing: 'text-info border-info-border bg-info-surface',
  processing: 'text-secondary border-border bg-surface-subtle',
  waiting: 'text-muted-foreground border-border bg-muted',
  completed: 'text-success border-success-border bg-success-surface',
  locked: 'text-muted-foreground border-border bg-muted',
  failed: 'text-danger border-danger-border bg-danger-surface',
  'low-confidence': 'text-warning border-warning-border bg-warning-surface',
} as const;
const qualities = {
  best: 'text-move-best',
  excellent: 'text-move-excellent',
  good: 'text-move-good',
  book: 'text-move-book',
  inaccuracy: 'text-move-inaccuracy',
  mistake: 'text-move-mistake',
  blunder: 'text-move-blunder',
  forced: 'text-move-forced',
  unknown: 'text-move-unknown',
} as const;
export type Status = keyof typeof statuses;
export type MoveQuality = keyof typeof qualities;
export function StatusBadge({ status }: { status: Status }) {
  return <Badge className={cn('capitalize', statuses[status])}>{status.replace('-', ' ')}</Badge>;
}
export function MoveQualityBadge({ quality }: { quality: MoveQuality }) {
  return (
    <Badge className={cn('capitalize bg-surface-subtle', qualities[quality])}>{quality}</Badge>
  );
}
export function MetricCard({
  label,
  value,
  helper,
}: {
  label: string;
  value: string;
  helper?: string;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="mt-2 font-mono text-2xl font-semibold tabular-nums">{value}</p>
        {helper ? <p className="mt-1 text-sm text-muted-foreground">{helper}</p> : null}
      </CardContent>
    </Card>
  );
}
export function DataValue({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'positive' | 'negative' | 'neutral';
}) {
  return (
    <span
      className={cn(
        'font-mono tabular-nums',
        tone === 'positive' && 'text-success',
        tone === 'negative' && 'text-danger',
      )}
    >
      {children}
    </span>
  );
}
