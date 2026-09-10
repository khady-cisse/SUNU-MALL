import { type ReactNode } from "react";
import { ChevronUp, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Pagination } from "./Pagination";
import { Skeleton } from "./Skeleton";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";

export type SortDirection = "asc" | "desc" | null;

export interface Column<T> {
  key: string;
  label: string;
  sortable?: boolean;
  className?: string;
  render?: (row: T, index: number) => ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  loading?: boolean;
  error?: Error | null;
  page?: number;
  totalPages?: number;
  onPageChange?: (page: number) => void;
  sortField?: string;
  sortDir?: SortDirection;
  onSort?: (key: string) => void;
  onRetry?: () => void;
  keyExtractor?: (row: T, index: number) => string;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyIcon?: ReactNode;
  pageSizeOptions?: number[];
  pageSize?: number;
  onPageSizeChange?: (size: number) => void;
  totalItems?: number;
  onRowClick?: (row: T) => void;
  className?: string;
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDirection }) {
  if (!active) return <span className="ml-1 text-muted-foreground/40"><ChevronUp className="h-3 w-3" /></span>;
  return dir === "asc"
    ? <ChevronUp className="ml-1 h-3 w-3 text-orange-600" />
    : <ChevronDown className="ml-1 h-3 w-3 text-orange-600" />;
}

function SkeletonRows({ columns, rows = 5 }: { columns: Column<unknown>[]; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <tr key={i} className="border-b border-border last:border-0">
          {columns.map((col) => (
            <td key={col.key} className="px-4 py-3">
              <Skeleton className="h-4 w-full rounded" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  loading,
  error,
  page,
  totalPages,
  onPageChange,
  sortField,
  sortDir,
  onSort,
  onRetry,
  keyExtractor,
  emptyTitle = "Aucun résultat trouvé",
  emptyDescription,
  emptyIcon,
  pageSizeOptions,
  pageSize,
  onPageSizeChange,
  totalItems,
  onRowClick,
  className,
}: DataTableProps<T>) {
  if (error) {
    return <ErrorState message={error.message} onRetry={onRetry} />;
  }

  if (!loading && data.length === 0) {
    return <EmptyState icon={emptyIcon ? () => <>{emptyIcon}</> : undefined} title={emptyTitle} description={emptyDescription} />;
  }

  return (
    <div className={cn("space-y-3", className)}>
      <div className="overflow-x-auto rounded-xl border border-border bg-white">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={cn(
                    "whitespace-nowrap px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground",
                    col.sortable && "cursor-pointer select-none hover:text-ink",
                    col.className,
                  )}
                  onClick={col.sortable ? () => onSort?.(col.key) : undefined}
                >
                  <span className="inline-flex items-center">
                    {col.label}
                    {col.sortable &&               <SortIcon active={sortField === col.key} dir={sortDir ?? null} />}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <SkeletonRows columns={columns as Column<unknown>[]} />
            ) : (
              data.map((row, i) => (
                <tr
                  key={keyExtractor ? keyExtractor(row, i) : i}
                  className={cn(
                    "border-b border-border last:border-0 transition-colors",
                    onRowClick && "cursor-pointer hover:bg-muted/30",
                  )}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                >
                  {columns.map((col) => (
                    <td key={col.key} className={cn("px-4 py-3 text-sm", col.className)}>
                      {col.render ? col.render(row, i) : String(row[col.key] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {totalItems != null && <span>{totalItems} résultat{totalItems > 1 ? "s" : ""}</span>}
          {pageSizeOptions && onPageSizeChange && (
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="rounded border border-border bg-white px-1.5 py-0.5 text-xs"
            >
              {pageSizeOptions.map((s) => (
                <option key={s} value={s}>{s} / page</option>
              ))}
            </select>
          )}
        </div>
        {page != null && totalPages != null && onPageChange && (
          <Pagination page={page} totalPages={totalPages} onPageChange={onPageChange} />
        )}
      </div>
    </div>
  );
}
