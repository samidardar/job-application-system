"use client";

import { useEffect, useState, useRef } from "react";
import { pipelineApi } from "@/lib/api";
import { toast } from "sonner";
import { Zap, CheckCircle, XCircle, Clock, RefreshCw } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";

interface PipelineRun {
  id: string;
  triggered_by: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  jobs_scraped: number;
  jobs_matched: number;
  cvs_generated: number;
  letters_generated: number;
  applications_submitted: number;
  errors_count: number;
}

const AGENT_STEPS = [
  { key: "scraping", label: "Scraping", desc: "LinkedIn, Indeed, WTTJ (24h)" },
  { key: "matching", label: "Matching IA", desc: "Score 0-100 par Claude" },
  { key: "cv_optimizer", label: "Optimisation CV", desc: "CV taillé ATS par offre" },
  { key: "cover_letter", label: "Lettre de motivation", desc: "Lettre FR personnalisée" },
  { key: "application", label: "Soumission", desc: "Playwright auto-fill" },
  { key: "followup", label: "Suivi J+7", desc: "Relance automatique" },
];

const StatusIcon = ({ status }: { status: string }) => {
  if (status === "success") return <CheckCircle className="h-5 w-5 text-emerald-500" />;
  if (status === "failed") return <XCircle className="h-5 w-5 text-red-500" />;
  if (status === "running") return <RefreshCw className="h-5 w-5 text-amber-500 animate-spin" />;
  return <Clock className="h-5 w-5 text-gray-400" />;
};

export default function PipelinePage() {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [events, setEvents] = useState<string[]>([]);
  const esRef = useRef<EventSource | null>(null);

  const loadRuns = async () => {
    try {
      const res = await pipelineApi.getRuns();
      setRuns(res.data);
    } catch {
      toast.error("Erreur lors du chargement");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRuns();

    // Connect to SSE
    const token = localStorage.getItem("access_token");
    if (token) {
      const url = pipelineApi.getStreamUrl();
      const es = new EventSource(url);
      esRef.current = es;

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.event !== "heartbeat" && data.event !== "connected") {
            setEvents((prev) => [JSON.stringify(data), ...prev.slice(0, 19)]);
            if (data.event === "pipeline_complete") {
              loadRuns();
            }
          }
        } catch {}
      };

      es.onerror = () => {
        es.close();
      };

      return () => {
        es.close();
      };
    }
  }, []);

  const trigger = async () => {
    setTriggering(true);
    try {
      await pipelineApi.trigger();
      toast.success("Pipeline démarré !");
      setTimeout(loadRuns, 2000);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Erreur");
    } finally {
      setTriggering(false);
    }
  };

  const latestRun = runs[0];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-postulio-blue">Pipeline IA</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Exécution quotidienne automatique à 8h00 • {runs.length} exécution(s) au total
          </p>
        </div>
        <button
          onClick={trigger}
          disabled={triggering}
          className="flex items-center gap-2 bg-postulio-teal text-white px-4 py-2.5 rounded-lg font-medium hover:bg-teal-700 transition disabled:opacity-60"
        >
          <Zap className="h-4 w-4" />
          {triggering ? "Démarrage..." : "Lancer maintenant"}
        </button>
      </div>

      {/* Pipeline steps visualization */}
      <div className="bg-white rounded-xl border p-6 shadow-sm">
        <h2 className="font-semibold text-postulio-blue mb-5">Étapes du pipeline quotidien</h2>
        <div className="flex items-start gap-0">
          {AGENT_STEPS.map((step, i) => (
            <div key={step.key} className="flex-1 flex flex-col items-center">
              <div className="flex items-center w-full">
                <div className="flex-1 h-0.5 bg-gray-200" style={{ visibility: i === 0 ? "hidden" : "visible" }} />
                <div className="w-10 h-10 rounded-full bg-postulio-teal/10 border-2 border-postulio-teal flex items-center justify-center flex-shrink-0">
                  <span className="text-xs font-bold text-postulio-teal">{i + 1}</span>
                </div>
                <div className="flex-1 h-0.5 bg-gray-200" style={{ visibility: i === AGENT_STEPS.length - 1 ? "hidden" : "visible" }} />
              </div>
              <div className="text-center mt-2 px-1">
                <div className="text-xs font-semibold text-postulio-blue">{step.label}</div>
                <div className="text-xs text-muted-foreground mt-0.5">{step.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Latest run stats */}
        {latestRun && (
          <div className="bg-white rounded-xl border p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <StatusIcon status={latestRun.status} />
              <h2 className="font-semibold text-postulio-blue">Dernière exécution</h2>
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Déclenchée par</span>
                <span className="font-medium capitalize">{latestRun.triggered_by}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Démarrée</span>
                <span className="font-medium">{formatDate(latestRun.started_at)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Offres scrapées</span>
                <span className="font-medium text-postulio-teal">{latestRun.jobs_scraped}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Offres matchées</span>
                <span className="font-medium text-postulio-teal">{latestRun.jobs_matched}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">CV générés</span>
                <span className="font-medium text-postulio-teal">{latestRun.cvs_generated}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Lettres générées</span>
                <span className="font-medium text-postulio-teal">{latestRun.letters_generated}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Candidatures soumises</span>
                <span className="font-bold text-postulio-blue">{latestRun.applications_submitted}</span>
              </div>
              {latestRun.errors_count > 0 && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Erreurs</span>
                  <span className="font-medium text-red-500">{latestRun.errors_count}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* SSE live events */}
        <div className="lg:col-span-2 bg-postulio-blue rounded-xl p-5 shadow-sm">
          <h2 className="font-semibold text-white mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
            Événements en direct
          </h2>
          <div className="space-y-1.5 max-h-[300px] overflow-y-auto">
            {events.length === 0 ? (
              <p className="text-white/40 text-sm">En attente d'événements... Lancez le pipeline !</p>
            ) : (
              events.map((e, i) => (
                <div key={i} className="text-xs text-white/70 font-mono bg-white/5 rounded px-2 py-1">
                  {e}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Run history */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="p-4 border-b">
          <h2 className="font-semibold text-postulio-blue">Historique des exécutions</h2>
        </div>
        <table className="w-full">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase">Statut</th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase">Démarrée</th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase">Scrapées</th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase">Matchées</th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase">Soumises</th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase">Déclencheur</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {runs.map((run) => (
              <tr key={run.id} className="hover:bg-gray-50">
                <td className="px-5 py-3">
                  <div className="flex items-center gap-2">
                    <StatusIcon status={run.status} />
                    <span className="text-sm capitalize">{run.status}</span>
                  </div>
                </td>
                <td className="px-5 py-3 text-sm text-muted-foreground">{formatDate(run.started_at)}</td>
                <td className="px-5 py-3 text-sm font-medium">{run.jobs_scraped}</td>
                <td className="px-5 py-3 text-sm font-medium">{run.jobs_matched}</td>
                <td className="px-5 py-3 text-sm font-medium text-postulio-teal">{run.applications_submitted}</td>
                <td className="px-5 py-3 text-xs text-muted-foreground capitalize">{run.triggered_by}</td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr>
                <td colSpan={6} className="text-center py-8 text-muted-foreground text-sm">
                  Aucune exécution. Lancez votre premier pipeline !
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
