import { type InputHTMLAttributes, forwardRef } from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

interface SearchInputProps extends InputHTMLAttributes<HTMLInputElement> {
  onClear?: () => void;
}

export const SearchInput = forwardRef<HTMLInputElement, SearchInputProps>(
  ({ className, onClear, value, ...props }, ref) => {
    return (
      <div className={cn("relative", className)}>
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          ref={ref}
          type="text"
          value={value}
          className="h-10 w-full rounded-lg border border-border bg-white pl-9 pr-9 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-orange-400 focus:ring-2 focus:ring-orange-100"
          {...props}
        />
        {value && onClear && (
          <button
            onClick={onClear}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-ink"
          >
            &times;
          </button>
        )}
      </div>
    );
  },
);
SearchInput.displayName = "SearchInput";
