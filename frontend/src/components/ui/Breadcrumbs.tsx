import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export interface BreadcrumbItem {
  label: string;
  to?: string;
}

interface BreadcrumbsProps {
  items: BreadcrumbItem[];
  className?: string;
}

export function Breadcrumbs({ items, className }: BreadcrumbsProps) {
  return (
    <nav aria-label="Fil d'Ariane" className={cn("flex items-center gap-1 text-sm text-muted-foreground", className)}>
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        return (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
            {item.to && !isLast ? (
              <Link to={item.to} className="hover:text-orange-600 transition-colors">
                {item.label}
              </Link>
            ) : (
              <span className={cn(isLast ? "font-medium text-ink" : "")}>{item.label}</span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
