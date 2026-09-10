import { type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/utils";

export interface TimelineEntry {
  date: string;
  actor?: string;
  actorRole?: string;
  action: string;
  label?: string;
  detail?: string;
  icon?: ReactNode;
}

interface TimelineProps {
  entries: TimelineEntry[];
  className?: string;
}

export function Timeline({ entries, className }: TimelineProps) {
  if (!entries.length) {
    return <p className="py-4 text-center text-sm text-muted-foreground">Aucun historique.</p>;
  }

  return (
    <div className={cn("relative space-y-0", className)}>
      <div className="absolute left-[15px] top-2 bottom-2 w-px bg-border" />
      {entries.map((entry, i) => (
        <div key={i} className="relative flex gap-4 pb-6 last:pb-0">
          <div className="relative z-10 flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-full border-2 border-border bg-white">
            {entry.icon ?? <span className="h-2 w-2 rounded-full bg-orange-400" />}
          </div>
          <div className="min-w-0 flex-1 pt-0.5">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-sm font-medium text-ink">{entry.action}</span>
              {entry.label && <span className="text-sm text-muted-foreground">{entry.label}</span>}
            </div>
            {entry.actor && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                {entry.actor}
                {entry.actorRole && <span className="ml-1 text-muted-foreground/60">({entry.actorRole})</span>}
              </p>
            )}
            {entry.detail && <p className="mt-1 text-sm text-muted-foreground">{entry.detail}</p>}
            <time className="mt-1 block text-xs text-muted-foreground/70">{formatDate(entry.date)}</time>
          </div>
        </div>
      ))}
    </div>
  );
}
