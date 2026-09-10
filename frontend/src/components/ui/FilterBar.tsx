import { type ReactNode } from "react";
import { RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "./Button";

export interface FilterOption {
  value: string;
  label: string;
}

interface FilterBarProps {
  filters: { key: string; label: string; options: FilterOption[]; value: string }[];
  onChange: (key: string, value: string) => void;
  onReset?: () => void;
  children?: ReactNode;
  className?: string;
}

export function FilterBar({ filters, onChange, onReset, children, className }: FilterBarProps) {
  const hasActiveFilter = filters.some((f) => f.value !== "" && f.value !== "all");

  return (
    <div className={cn("flex flex-wrap items-center gap-3", className)}>
      {filters.map((f) => (
        <div key={f.key} className="flex items-center gap-1.5">
          <label className="text-xs font-medium text-muted-foreground">{f.label}</label>
          <select
            value={f.value}
            onChange={(e) => onChange(f.key, e.target.value)}
            className="h-8 rounded-lg border border-border bg-white px-2 text-xs outline-none focus:border-orange-400"
          >
            {f.options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      ))}
      {hasActiveFilter && onReset && (
        <Button variant="ghost" size="sm" onClick={onReset} className="gap-1 text-xs">
          <RotateCcw className="h-3 w-3" />
          Réinitialiser
        </Button>
      )}
      {children}
    </div>
  );
}
