"use client";

import { useEffect, useState, useCallback } from "react";
import { dashboardApi, pipelineApi } from "@/lib/api";
import { toast } from "sonner";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { Zap, TrendingUp, FileText, Calendar, BarChart2, Award } from "lucide-react";
import { cn, STATUS_COLORS, STATUS_LABELS, PLATFORM_LABELS, getScoreClass } from "@/lib/utils";

const PLATFORM_COLORS = ["#0d9488", "#0f172a", "#6366f1"];

interface Metrics {
  total_applications: number;
  applications_this_month: number;
  response_rate: number;
  interviews_count: number;
  avg_match_score: number | null;
  pipeline_today: {
    status: string;
    scraped: number;
    matched: number;
    applied: number;
    started_at: string;
  } | null;
  daily_stats_7d: Array<{ date: string; scraped: number; matched: number; applied: number }>;
  platform_breakdown: Array<{ platform: string; count: number }>;
  top_opportunities: Array<{
    id: string;
    title: string;
    company: string;
    platform: string;
    match_score: number;
    job_type: string;
    status: string;
  }>;
  recent_activity: Array<{
    type: string;
    timestamp: string;
    status: string;
    scraped: number;
    matched: number;
    applied: number;
  }>;
}

function MetricCard({
  label,
  value,
  icon: Icon,
  sub,
  color = "text-postulio-teal",
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="bg-white rounded-xl border p-5 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-muted-foreground">{label}</span>
        <div className={cn("p-2 rounded-lg bg-muted", color)}>
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <div className="text-2xl font-bold text-postulio-blue">{value}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </div>
  );
}

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [jobTitle, setJobTitle] = useState("");
  const [location, setLocation] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await dashboardApi.getMetrics();
      setMetrics(res.data);
    } catch {
      toast.error("Erreur lors du chargement des métriques");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const triggerPipeline = async () => {
    if (!jobTitle.trim() || !location.trim()) {
      setShowSearch(true);
      return;
    }
    setTriggering(true);
    setShowSearch(false);
    try {
      await pipelineApi.trigger({ job_title: jobTitle, location });
      toast.success("Pipeline démarré ! Les offres apparaîtront dans l'onglet Offres.");
      setTimeout(load, 3000);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Erreur lors du démarrage");
    } finally {
      setTriggering(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-24 bg-gray-200 rounded-xl" />
        ))}
      </div>
    );
  }

  const platformData = (metrics?.platform_breakdown || []).map((p) => ({
    ...p,
    name: PLATFORM_LABELS[p.platform] || p.platform,
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-postulio-blue">Dashboard</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Vue d'ensemble de vos candidatures automatisées
          </p>
        </div>
        <button
          onClick={() => setShowSearch(true)}
          disabled={triggering}
          className="flex items-center gap-2 bg-postulio-teal text-white px-4 py-2.5 rounded-lg font-medium hover:bg-teal-700 transition disabled:opacity-60 shadow-sm"
        >
          <Zap className="h-4 w-4" />
          {triggering ? "Scraping en cours…" : "Nouvelle recherche"}
        </button>
      </div>

      {/* Search form */}
      {showSearch && (
        <div className="bg-white rounded-xl border shadow-sm p-5">
          <h3 className="font-semibold text-postulio-blue mb-3">Lancer une recherche</h3>
          <div className="flex gap-3 flex-wrap">
            <input
              type="text"
              placeholder="Titre du poste (ex: Data Scientist)"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              className="flex-1 min-w-48 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-postulio-teal"
            />
            <input
              type="text"
              placeholder="Localisation (ex: Paris, France)"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className="flex-1 min-w-48 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-postulio-teal"
            />
            <button
              onClick={triggerPipeline}
              disabled={triggering || !jobTitle.trim() || !location.trim()}
              className="flex items-center gap-2 bg-postulio-teal text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-teal-700 transition disabled:opacity-60"
            >
              <Zap className="h-4 w-4" />
              {triggering ? "En cours…" : "Scraper maintenant"}
            </button>
            <button onClick={() => setShowSearch(false)} className="text-sm text-muted-foreground hover:text-postulio-blue transition px-2">
              Annuler
            </button>
          </div>
        </div>
      )}

      {/* Pipeline status banner */}
      {metrics?.pipeline_today && (
        <div className="bg-postulio-blue text-white rounded-xl p-4 flex items-center gap-6">
          <div className="flex-1">
            <div className="text-sm font-medium text-white/70">Dernier pipeline</div>
            <div className="flex items-center gap-2 mt-1">
              <span className={cn(
                "text-xs px-2 py-0.5 rounded-full",
                metrics.pipeline_today.status === "success" ? "bg-emerald-500" :
                metrics.pipeline_today.status === "running" ? "bg-amber-500 animate-pulse-slow" :
                "bg-red-500"
              )}>
                {metrics.pipeline_today.status}
              </span>
              <span className="text-sm">
                Démarré à {new Date(metrics.pipeline_today.started_at).toLocaleTimeString("fr-FR")}
              </span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-6 text-center">
            {[
              { label: "Scrapées", value: metrics.pipeline_today.scraped },
              { label: "Matchées", value: metrics.pipeline_today.matched },
              { label: "Soumises", value: metrics.pipeline_today.applied },
            ].map(({ label, value }) => (
              <div key={label}>
                <div className="text-2xl font-bold">{value}</div>
                <div className="text-xs text-white/60">{label}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Candidatures totales"
          value={metrics?.total_applications || 0}
          icon={FileText}
        />
        <MetricCard
          label="Ce mois-ci"
          value={metrics?.applications_this_month || 0}
          icon={Calendar}
          color="text-blue-500"
        />
        <MetricCard
          label="Taux de réponse"
          value={`${metrics?.response_rate || 0}%`}
          icon={TrendingUp}
          color="text-purple-500"
        />
        <MetricCard
          label="Entretiens"
          value={metrics?.interviews_count || 0}
          icon={Award}
          color="text-amber-500"
          sub={metrics?.avg_match_score ? `Score moyen: ${metrics.avg_match_score}` : undefined}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 7-day bar chart */}
        <div className="lg:col-span-2 bg-white rounded-xl border p-5 shadow-sm">
          <h2 className="font-semibold text-postulio-blue mb-4 flex items-center gap-2">
            <BarChart2 className="h-4 w-4" />
            Activité 7 derniers jours
          </h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={metrics?.daily_stats_7d || []}>
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="scraped" fill="#e2e8f0" name="Scrapées" radius={[3, 3, 0, 0]} />
              <Bar dataKey="matched" fill="#0d9488" name="Matchées" radius={[3, 3, 0, 0]} />
              <Bar dataKey="applied" fill="#0f172a" name="Soumises" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Platform pie */}
        <div className="bg-white rounded-xl border p-5 shadow-sm">
          <h2 className="font-semibold text-postulio-blue mb-4">Plateformes</h2>
          {platformData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={platformData} dataKey="count" nameKey="name" cx="50%" cy="50%" outerRadius={70} label>
                  {platformData.map((_, i) => (
                    <Cell key={i} fill={PLATFORM_COLORS[i % PLATFORM_COLORS.length]} />
                  ))}
                </Pie>
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-[200px] text-muted-foreground text-sm">
              Aucune donnée
            </div>
          )}
        </div>
      </div>

      {/* Top opportunities */}
      <div className="bg-white rounded-xl border shadow-sm">
        <div className="p-5 border-b">
          <h2 className="font-semibold text-postulio-blue">Top opportunités</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Offres avec les meilleurs scores de correspondance</p>
        </div>
        <div className="divide-y">
          {(metrics?.top_opportunities || []).slice(0, 8).map((job) => (
            <div key={job.id} className="flex items-center px-5 py-3 hover:bg-gray-50 transition">
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm truncate">{job.title}</div>
                <div className="text-xs text-muted-foreground">{job.company} · {PLATFORM_LABELS[job.platform]}</div>
              </div>
              <div className="flex items-center gap-3 ml-4">
                <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", getScoreClass(job.match_score))}>
                  {job.match_score}%
                </span>
                <span className={cn("text-xs px-2 py-0.5 rounded-full", STATUS_COLORS[job.status] || "bg-gray-100")}>
                  {STATUS_LABELS[job.status] || job.status}
                </span>
              </div>
            </div>
          ))}
          {(metrics?.top_opportunities || []).length === 0 && (
            <div className="text-center py-8 text-muted-foreground text-sm">
              Aucune opportunité trouvée. Lancez le pipeline pour commencer !
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
