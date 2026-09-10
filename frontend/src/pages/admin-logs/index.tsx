import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { SearchInput } from "@/components/ui/SearchInput";

const MOCK_LOGS = [
  { timestamp: "2026-09-08 14:32:15", service: "backend", level: "INFO", message: "GET /api/orders/ 200 OK", request_id: "REQ-20260908-A82F91" },
  { timestamp: "2026-09-08 14:32:16", service: "backend", level: "INFO", message: "POST /api/payments/webhook/wave/ 200 OK", request_id: "REQ-20260908-B3C7D2" },
  { timestamp: "2026-09-08 14:33:01", service: "celery", level: "WARNING", message: "Task timeout: send_notification (30s)", request_id: "REQ-20260908-E4F5G6" },
  { timestamp: "2026-09-08 14:35:22", service: "backend", level: "ERROR", message: "500 Internal Server Error: /api/payments/webhook/orange_money/", request_id: "REQ-20260908-H7I8J9" },
  { timestamp: "2026-09-08 14:36:00", service: "redis", level: "INFO", message: "Connection pool: 5 active, 10 idle", request_id: "" },
];

const LEVEL_COLORS: Record<string, string> = {
  INFO: "text-blue-600 bg-blue-50",
  WARNING: "text-amber-600 bg-amber-50",
  ERROR: "text-red-600 bg-red-50",
  CRITICAL: "text-red-800 bg-red-100",
};

export default function AdminLogsPage() {
  const [filter, setFilter] = useState("");
  const [level, setLevel] = useState("");

  const filteredLogs = MOCK_LOGS.filter((log) => {
    if (level && log.level !== level) return false;
    if (filter && !log.message.toLowerCase().includes(filter.toLowerCase()) && !log.request_id.toLowerCase().includes(filter.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Logs" }]} />
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <SearchInput placeholder="Filtrer par message ou Request ID..." value={filter} onChange={(e) => setFilter(e.target.value)} onClear={() => setFilter("")} className="max-w-md" />
          <select value={level} onChange={(e) => setLevel(e.target.value)} className="rounded-lg border border-border bg-white px-3 py-2 text-sm">
            <option value="">Tous les niveaux</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
        </div>
        <div className="mt-4 overflow-x-auto rounded-xl border border-border">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="px-4 py-3 text-xs font-semibold uppercase text-muted-foreground">Timestamp</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase text-muted-foreground">Service</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase text-muted-foreground">Niveau</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase text-muted-foreground">Message</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase text-muted-foreground">Request ID</th>
              </tr>
            </thead>
            <tbody>
              {filteredLogs.map((log, i) => (
                <tr key={i} className="border-b border-border last:border-0">
                  <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">{log.timestamp}</td>
                  <td className="px-4 py-2.5 text-sm">{log.service}</td>
                  <td className="px-4 py-2.5"><span className={`rounded px-2 py-0.5 text-xs font-bold ${LEVEL_COLORS[log.level]}`}>{log.level}</span></td>
                  <td className="px-4 py-2.5 text-sm max-w-[400px] truncate">{log.message}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">{log.request_id}</td>
                </tr>
              ))}
              {filteredLogs.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-sm text-muted-foreground">Aucune log trouvée.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
