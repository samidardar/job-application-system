"use client";

import { useEffect, useState } from "react";
import { applicationsApi } from "@/lib/api";
import { toast } from "sonner";
import { cn, STATUS_COLORS, STATUS_LABELS, formatDate, timeAgo } from "@/lib/utils";

const KANBAN_COLUMNS = [
  { key: "submitted", label: "Soumises" },
  { key: "viewed", label: "Vues" },
  { key: "interview_scheduled", label: "Entretiens" },
  { key: "offer_received", label: "Offres" },
  { key: "rejected", label: "Refusées" },
];

interface Application {
  id: string;
  job_id: string;
  status: string;
  submitted_at: string | null;
  follow_up_due_at: string | null;
  timeline: Array<{ event: string; timestamp: string }>;
}

export default function ApplicationsPage() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"kanban" | "list">("kanban");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await applicationsApi.list();
        setApplications(res.data);
      } catch {
        toast.error("Erreur lors du chargement");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const updateStatus = async (id: string, status: string) => {
    try {
      await applicationsApi.update(id, { status });
      setApplications((apps) =>
        apps.map((a) => (a.id === id ? { ...a, status } : a))
      );
      toast.success("Statut mis à jour");
    } catch {
      toast.error("Erreur lors de la mise à jour");
    }
  };

  if (loading) {
    return <div className="animate-pulse space-y-4"><div className="h-64 bg-gray-200 rounded-xl" /></div>;
  }

  const grouped = KANBAN_COLUMNS.reduce(
    (acc, col) => ({
      ...acc,
      [col.key]: applications.filter((a) => a.status === col.key),
    }),
    {} as Record<string, Application[]>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-postulio-blue">Candidatures</h1>
          <p className="text-muted-foreground text-sm mt-1">{applications.length} candidature(s) au total</p>
        </div>
        <div className="flex border rounded-lg overflow-hidden">
          {(["kanban", "list"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                "px-3 py-1.5 text-sm font-medium capitalize transition",
                view === v ? "bg-postulio-teal text-white" : "text-muted-foreground hover:bg-gray-100"
              )}
            >
              {v === "kanban" ? "Kanban" : "Liste"}
            </button>
          ))}
        </div>
      </div>

      {view === "kanban" ? (
        <div className="grid grid-cols-5 gap-4">
          {KANBAN_COLUMNS.map((col) => (
            <div key={col.key} className="bg-gray-100 rounded-xl p-3">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm text-postulio-blue">{col.label}</h3>
                <span className="text-xs bg-white text-muted-foreground rounded-full px-2 py-0.5">
                  {grouped[col.key]?.length || 0}
                </span>
              </div>
              <div className="space-y-2">
                {(grouped[col.key] || []).map((app) => (
                  <div key={app.id} className="bg-white rounded-lg p-3 shadow-sm border border-gray-200">
                    <div className="text-xs text-muted-foreground mb-1">
                      {timeAgo(app.submitted_at)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {app.follow_up_due_at && (
                        <span className="text-amber-600">
                          Relance: {formatDate(app.follow_up_due_at)}
                        </span>
                      )}
                    </div>
                    <select
                      value={app.status}
                      onChange={(e) => updateStatus(app.id, e.target.value)}
                      className="mt-2 text-xs border rounded px-1 py-0.5 w-full"
                    >
                      {KANBAN_COLUMNS.map((c) => (
                        <option key={c.key} value={c.key}>{c.label}</option>
                      ))}
                    </select>
                  </div>
                ))}
                {(grouped[col.key] || []).length === 0 && (
                  <div className="text-xs text-muted-foreground text-center py-4">Vide</div>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Candidature</th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Statut</th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Soumise</th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Relance</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {applications.map((app) => (
                <tr key={app.id} className="hover:bg-gray-50">
                  <td className="px-5 py-3 text-sm font-medium">{app.job_id.slice(0, 8)}...</td>
                  <td className="px-5 py-3">
                    <span className={cn("text-xs px-2 py-0.5 rounded-full", STATUS_COLORS[app.status])}>
                      {STATUS_LABELS[app.status] || app.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-sm text-muted-foreground">{formatDate(app.submitted_at)}</td>
                  <td className="px-5 py-3 text-sm text-muted-foreground">{formatDate(app.follow_up_due_at)}</td>
                </tr>
              ))}
              {applications.length === 0 && (
                <tr>
                  <td colSpan={4} className="text-center py-10 text-muted-foreground text-sm">
                    Aucune candidature. Lancez le pipeline pour démarrer !
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
