import { type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Card } from "./Card";

type Tone = "orange" | "green" | "blue" | "red" | "purple" | "gray";

const toneClasses: Record<Tone, { bg: string; icon: string; text: string }> = {
  orange: { bg: "bg-orange-50", icon: "text-orange-600", text: "text-orange-700" },
  green: { bg: "bg-green-50", icon: "text-green-600", text: "text-green-700" },
  blue: { bg: "bg-blue-50", icon: "text-blue-600", text: "text-blue-700" },
  red: { bg: "bg-red-50", icon: "text-red-600", text: "text-red-700" },
  purple: { bg: "bg-purple-50", icon: "text-purple-600", text: "text-purple-700" },
  gray: { bg: "bg-gray-50", icon: "text-gray-600", text: "text-gray-700" },
};

interface StatCardProps {
  label: string;
  value: string | number;
  icon?: ReactNode;
  tone?: Tone;
  className?: string;
  subtitle?: string;
}

export function StatCard({ label, value, icon, tone = "orange", className, subtitle }: StatCardProps) {
  const t = toneClasses[tone];
  return (
    <Card className={cn("flex items-start gap-4", className)}>
      {icon && (
        <div className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-lg", t.bg)}>
          <span className={t.icon}>{icon}</span>
        </div>
      )}
      <div className="min-w-0">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className={cn("text-2xl font-bold", t.text)}>{value}</p>
        {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
      </div>
    </Card>
  );
}
