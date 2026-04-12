import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  ExternalLink,
  Download,
  FileText,
  Mail,
  ArrowLeft,
  MessageCircle,
  TrendingUp,
  Users,
  Briefcase,
  Target,
  RefreshCw,
  LogOut,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import VideoBackground from "@/components/VideoBackground";
import FloatingP from "@/components/FloatingP";
import BubbleNav from "@/components/BubbleNav";
import OnboardingSection from "@/components/OnboardingSection";
import logo from "@/assets/logo.png";
import { dashboard, pipeline, auth, users, ApiError } from "@/lib/api";
import type { DashboardMetrics } from "@/lib/api";

// ─── Types for war-room response ─────────────────────────────────────────────

interface PipelineLive {
  run_id: string;
  status: string;
  started_at: string;
  jobs_scraped: number;
  jobs_matched: number;
  applications_submitted: number;
}

interface Funnel30d {
  scraped: number;
  matched: number;
  docs_ready: number;
  applied: number;
  rejected: number;
}

interface Today {
  scraped: number;
  applied: number;
}

interface TopJob {
  id: string;
  title: string;
  company: string;
  platform: string;
  match_score: number;
  status: string;
  application_url: string | null;
}

interface PendingFollowup {
  application_id: string;
  job_title: string;
  company: string;
  submitted_at: string | null;
  days_waiting: number | null;
  application_url: string | null;
}

interface RecentRun {
  run_id: string;
  status: string;
  started_at: string;
  jobs_scraped: number;
  jobs_matched: number;
  applied: number;
}

interface WarRoom {
  pipeline_live: PipelineLive | null;
  is_pipeline_running: boolean;
  funnel_30d: Funnel30d;
  today: Today;
  top_opportunities: TopJob[];
  pending_followups: PendingFollowup[];
  recent_runs: RecentRun[];
}

// ─── Status label helper ──────────────────────────────────────────────────────

const statusLabel: Record<string, { text: string; cls: string }> = {
  scraped: { text: "Nouveau", cls: "text-primary bg-primary/10" },
  matched: { text: "Matché", cls: "text-blue-400 bg-blue-400/10" },
  cv_generated: { text: "CV Prêt", cls: "text-cyan-400 bg-cyan-400/10" },
  letter_generated: { text: "LDM Prête", cls: "text-teal-400 bg-teal-400/10" },
  ready_to_apply: { text: "Prêt", cls: "text-emerald-400 bg-emerald-400/10" },
  applying: { text: "En cours", cls: "text-amber-400 bg-amber-400/10" },
  applied: { text: "Postulé", cls: "text-emerald-400 bg-emerald-400/10" },
  failed: { text: "Échec", cls: "text-red-400 bg-red-400/10" },
  skipped: { text: "Ignoré", cls: "text-zinc-400 bg-zinc-400/10" },
  below_threshold: { text: "Refusé", cls: "text-red-400 bg-red-400/10" },
};

// ─── Platform colors for pie chart ───────────────────────────────────────────

const PLATFORM_COLORS: Record<string, string> = {
  linkedin: "hsl(220, 100%, 56%)",
  indeed: "hsl(200, 80%, 50%)",
  welcometothejungle: "hsl(160, 70%, 45%)",
  francetravail: "hsl(250, 70%, 55%)",
  bonne_alternance: "hsl(30, 80%, 55%)",
};

// ─── Dashboard component ──────────────────────────────────────────────────────

const Dashboard = () => {
  const navigate = useNavigate();
  const [warRoom, setWarRoom] = useState<WarRoom | null>(null);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [onboarded, setOnboarded] = useState(false);
  const [checkingProfile, setCheckingProfile] = useState(true);

  // Check if user already has a profile with CV data
  useEffect(() => {
    const checkProfile = async () => {
      try {
        const profile = await users.profile();
        // If they have skills or experience, they've already onboarded
        if (
          (profile.skills_technical && profile.skills_technical.length > 0) ||
          (profile.experience && profile.experience.length > 0)
        ) {
          setOnboarded(true);
        }
      } catch {
        // Profile not found or 401 — show onboarding
      } finally {
        setCheckingProfile(false);
      }
    };
    void checkProfile();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [wr, m] = await Promise.all([
        dashboard.warRoom() as unknown as Promise<WarRoom>,
        dashboard.metrics(),
      ]);
      setWarRoom(wr);
      setMetrics(m);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        auth.logout();
        navigate("/login");
        return;
      }
      setError(err instanceof ApiError ? err.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchData();
    const interval = setInterval(() => { void fetchData(); }, 60_000);
    return () => clearInterval(interval);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const triggerPipeline = async () => {
    setTriggering(true);
    try {
      await pipeline.trigger();
      setTimeout(() => { void fetchData(); }, 2000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible de lancer le pipeline");
    } finally {
      setTriggering(false);
    }
  };

  const handleLogout = () => {
    auth.logout();
    navigate("/login");
  };

  const handleOnboardingComplete = async (data: { jobTitle: string; contractType: string | null; city: string }) => {
    // Update profile with job preferences
    try {
      await users.updateProfile({
        ville: data.city || null,
      });
    } catch {
      // Non-blocking — profile update is best-effort
    }
    setOnboarded(true);
    // Trigger pipeline after onboarding
    void triggerPipeline();
  };

  // ── Derived metrics ────────────────────────────────────────────────────────

  const funnel = warRoom?.funnel_30d;
  const today = warRoom?.today;
  const topJobs = warRoom?.top_opportunities ?? [];
  const recentRuns = warRoom?.recent_runs ?? [];

  const dailyStats = metrics?.daily_stats_7d ?? [];
  const platformBreakdown = metrics?.platform_breakdown ?? [];
  const pieData = platformBreakdown.map((p) => ({
    name: p.platform,
    value: p.count,
    color: PLATFORM_COLORS[p.platform] ?? "hsl(220, 60%, 50%)",
  }));

  const totalApps = metrics?.total_applications ?? 0;
  const responseRate = metrics?.response_rate ?? 0;
  const interviewsCount = metrics?.interviews_count ?? 0;
  const avgScore = metrics?.avg_match_score ?? null;

  return (
    <div className="h-screen flex flex-col relative overflow-hidden">
      <VideoBackground />
      <FloatingP />

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-5 py-4 border-b border-border/10 backdrop-blur-sm bg-background/20">
        <Link
          to="/"
          className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="text-xs font-light tracking-widest uppercase">Retour</span>
        </Link>
        <div className="flex items-center gap-2">
          <img src={logo} alt="Postulio" className="w-6 h-6" />
          <span className="text-xs font-medium tracking-[0.15em] uppercase text-foreground/70">Dashboard</span>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/chat"
            className="flex items-center gap-1.5 text-xs font-light tracking-widest uppercase text-muted-foreground hover:text-foreground transition-colors"
          >
            <MessageCircle className="w-3.5 h-3.5" />
            Consultant
          </Link>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 text-xs font-light text-muted-foreground hover:text-foreground transition-colors"
            title="Se déconnecter"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="relative z-10 px-4 py-2 bg-red-900/30 border-b border-red-500/20 text-xs text-red-400 font-light text-center">
          {error}
        </div>
      )}

      {/* Pipeline live banner */}
      {warRoom?.is_pipeline_running && (
        <div className="relative z-10 px-4 py-2 bg-primary/10 border-b border-primary/20 text-xs text-primary font-light text-center flex items-center justify-center gap-2">
          <RefreshCw className="w-3 h-3 animate-spin" />
          Pipeline en cours — {warRoom.pipeline_live?.jobs_scraped ?? 0} offres scrapées,{" "}
          {warRoom.pipeline_live?.applications_submitted ?? 0} candidatures soumises
        </div>
      )}

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto relative z-10">
        <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">

          {/* Onboarding section — first step */}
          {!checkingProfile && !onboarded && (
            <OnboardingSection onComplete={(data) => void handleOnboardingComplete(data)} />
          )}

          {/* Action bar */}
          <div className="flex items-center justify-between">
            <div className="text-xs font-light text-muted-foreground tracking-wide uppercase">
              Vue d'ensemble — 30 derniers jours
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => { void fetchData(); }}
                disabled={loading}
                className="flex items-center gap-1.5 text-xs font-light text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
                Actualiser
              </button>
              <button
                onClick={() => { void triggerPipeline(); }}
                disabled={triggering || warRoom?.is_pipeline_running}
                className="flex items-center gap-1.5 text-xs font-light px-3 py-1.5 rounded-full bg-primary/10 text-primary hover:bg-primary/20 transition-all disabled:opacity-50"
              >
                {triggering ? "Lancement…" : "Lancer le pipeline"}
              </button>
            </div>
          </div>

          {/* KPI cards */}
          <motion.div
            className="grid grid-cols-2 md:grid-cols-4 gap-3"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            {[
              {
                label: "Candidatures",
                value: loading ? "—" : totalApps.toString(),
                icon: Briefcase,
                sub: loading ? "" : `${today?.applied ?? 0} aujourd'hui`,
              },
              {
                label: "Taux de réponse",
                value: loading ? "—" : `${responseRate}%`,
                icon: TrendingUp,
                sub: loading ? "" : `${funnel?.matched ?? 0} matchés`,
              },
              {
                label: "Entretiens",
                value: loading ? "—" : interviewsCount.toString(),
                icon: Users,
                sub: loading ? "" : `${funnel?.applied ?? 0} postulés / 30j`,
              },
              {
                label: "Score moyen",
                value: loading ? "—" : avgScore !== null ? `${avgScore}%` : "N/A",
                icon: Target,
                sub: loading ? "" : `${funnel?.scraped ?? 0} scrapées / 30j`,
              },
            ].map((s, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.08 }}
                className="rounded-2xl border border-border/15 bg-card/20 backdrop-blur-sm p-4"
              >
                <s.icon className="w-4 h-4 text-primary/50 mb-2" />
                <p className="text-2xl font-extralight tabular">{s.value}</p>
                <p className="text-[10px] text-muted-foreground font-light tracking-wide uppercase mt-1">
                  {s.label}
                </p>
                <p className="text-[9px] text-primary/50 font-light mt-0.5">{s.sub}</p>
              </motion.div>
            ))}
          </motion.div>

          {/* Charts row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Area chart — daily stats 7d */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="md:col-span-2 rounded-2xl border border-border/15 bg-card/20 backdrop-blur-sm p-4"
            >
              <p className="text-xs font-light text-muted-foreground mb-4">
                Activité des 7 derniers jours
              </p>
              <ResponsiveContainer width="100%" height={160}>
                <AreaChart data={dailyStats}>
                  <defs>
                    <linearGradient id="blueGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="hsl(220, 100%, 56%)" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="hsl(220, 100%, 56%)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 9, fill: "hsl(0,0%,50%)" }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(d: string) => d.slice(5)}
                  />
                  <YAxis hide />
                  <Area
                    type="monotone"
                    dataKey="scraped"
                    stroke="hsl(220, 100%, 56%)"
                    strokeWidth={1.5}
                    fill="url(#blueGrad)"
                  />
                  <Area
                    type="monotone"
                    dataKey="applied"
                    stroke="hsl(220, 80%, 70%)"
                    strokeWidth={1}
                    fill="none"
                    strokeDasharray="4 4"
                  />
                </AreaChart>
              </ResponsiveContainer>
              <div className="flex gap-4 mt-2">
                <span className="text-[9px] text-muted-foreground flex items-center gap-1">
                  <span className="w-3 h-px bg-primary inline-block" /> Scrapées
                </span>
                <span className="text-[9px] text-muted-foreground flex items-center gap-1">
                  <span className="w-3 h-px bg-primary/50 inline-block" /> Postulées
                </span>
              </div>
            </motion.div>

            {/* Pie chart — platform breakdown */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="rounded-2xl border border-border/15 bg-card/20 backdrop-blur-sm p-4"
            >
              <p className="text-xs font-light text-muted-foreground mb-2">Répartition plateformes</p>
              {pieData.length > 0 ? (
                <>
                  <ResponsiveContainer width="100%" height={130}>
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={35}
                        outerRadius={55}
                        paddingAngle={3}
                        dataKey="value"
                        stroke="none"
                      >
                        {pieData.map((entry, i) => (
                          <Cell key={i} fill={entry.color} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="flex flex-col gap-1 mt-1">
                    {pieData.map((d) => (
                      <div key={d.name} className="flex items-center justify-between text-[10px]">
                        <span className="flex items-center gap-1.5 text-muted-foreground">
                          <span className="w-2 h-2 rounded-full" style={{ background: d.color }} />
                          {d.name}
                        </span>
                        <span className="text-foreground/70 tabular">{d.value}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="h-40 flex items-center justify-center text-xs text-muted-foreground/50">
                  {loading ? "Chargement…" : "Aucune donnée"}
                </div>
              )}
            </motion.div>
          </div>

          {/* Funnel bar chart */}
          {funnel && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.35 }}
              className="rounded-2xl border border-border/15 bg-card/20 backdrop-blur-sm p-4"
            >
              <p className="text-xs font-light text-muted-foreground mb-4">Entonnoir 30 jours</p>
              <ResponsiveContainer width="100%" height={100}>
                <BarChart
                  data={[
                    { name: "Scrapées", value: funnel.scraped },
                    { name: "Matchées", value: funnel.matched },
                    { name: "Docs prêts", value: funnel.docs_ready },
                    { name: "Postulées", value: funnel.applied },
                  ]}
                >
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 10, fill: "hsl(0,0%,50%)" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis hide />
                  <Bar dataKey="value" fill="hsl(220, 100%, 56%)" radius={[4, 4, 0, 0]} opacity={0.7} />
                </BarChart>
              </ResponsiveContainer>
            </motion.div>
          )}

          {/* Top opportunities table */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="rounded-2xl border border-border/15 bg-card/20 backdrop-blur-sm overflow-hidden"
          >
            <div className="px-4 py-3 border-b border-border/10 flex items-center justify-between">
              <p className="text-xs font-light text-muted-foreground tracking-wide uppercase">
                Meilleures opportunités
              </p>
              <span className="text-[10px] text-muted-foreground/50">{topJobs.length} offres</span>
            </div>
            {topJobs.length === 0 ? (
              <div className="px-4 py-8 text-center text-xs text-muted-foreground/50 font-light">
                {loading ? "Chargement…" : "Aucune offre matchée. Lancez le pipeline pour commencer."}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-border/10">
                      {["Poste", "Entreprise", "Plateforme", "Score", "Statut", "CV", "LDM", "Offre"].map((h) => (
                        <th
                          key={h}
                          className="px-4 py-3 text-[10px] font-medium text-muted-foreground tracking-wider uppercase whitespace-nowrap"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {topJobs.map((job, i) => {
                      const sl = statusLabel[job.status] ?? { text: job.status, cls: "text-muted-foreground bg-muted/10" };
                      return (
                        <motion.tr
                          key={job.id}
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: 0.45 + i * 0.03 }}
                          className="border-b border-border/5 hover:bg-card/20 transition-colors"
                        >
                          <td className="px-4 py-3 text-xs font-light text-foreground/90 whitespace-nowrap max-w-[200px] truncate">
                            {job.title}
                          </td>
                          <td className="px-4 py-3 text-xs font-light text-foreground/70 whitespace-nowrap">
                            {job.company}
                          </td>
                          <td className="px-4 py-3 text-xs font-light text-foreground/50 whitespace-nowrap">
                            {job.platform}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <span className="text-[10px] font-light text-primary tabular">
                              {job.match_score}%
                            </span>
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <span className={`text-[10px] font-light px-2 py-0.5 rounded-full ${sl.cls}`}>
                              {sl.text}
                            </span>
                          </td>
                          {/* CV download */}
                          <td className="px-4 py-3 whitespace-nowrap">
                            <button
                              className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-card/30 border border-border/10 text-[10px] font-light text-foreground/60 hover:text-foreground hover:border-border/30 transition-all"
                              title="Télécharger le CV"
                            >
                              <FileText className="w-3 h-3" />
                              CV
                              <Download className="w-2.5 h-2.5" />
                            </button>
                          </td>
                          {/* LDM download */}
                          <td className="px-4 py-3 whitespace-nowrap">
                            <button
                              className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-card/30 border border-border/10 text-[10px] font-light text-foreground/60 hover:text-foreground hover:border-border/30 transition-all"
                              title="Télécharger la lettre de motivation"
                            >
                              <Mail className="w-3 h-3" />
                              LDM
                              <Download className="w-2.5 h-2.5" />
                            </button>
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            {job.application_url ? (
                              <a
                                href={job.application_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary/10 text-primary text-[10px] font-light hover:bg-primary/20 transition-all"
                              >
                                Postuler
                                <ExternalLink className="w-3 h-3" />
                              </a>
                            ) : (
                              <span className="text-[10px] text-muted-foreground/30">—</span>
                            )}
                          </td>
                        </motion.tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </motion.div>

          {/* Recent pipeline runs */}
          {recentRuns.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 }}
              className="rounded-2xl border border-border/15 bg-card/20 backdrop-blur-sm overflow-hidden"
            >
              <div className="px-4 py-3 border-b border-border/10">
                <p className="text-xs font-light text-muted-foreground tracking-wide uppercase">
                  Exécutions récentes du pipeline
                </p>
              </div>
              <div className="divide-y divide-border/5">
                {recentRuns.map((run) => (
                  <div key={run.run_id} className="px-4 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span
                        className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                          run.status === "completed"
                            ? "bg-emerald-400"
                            : run.status === "running"
                            ? "bg-primary animate-pulse"
                            : run.status === "failed"
                            ? "bg-red-400"
                            : "bg-zinc-400"
                        }`}
                      />
                      <div>
                        <p className="text-xs font-light text-foreground/80">
                          {new Date(run.started_at).toLocaleString("fr-FR", {
                            day: "2-digit",
                            month: "2-digit",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </p>
                        <p className="text-[10px] text-muted-foreground/50 font-light">
                          {run.jobs_scraped} scrapées · {run.jobs_matched} matchées · {run.applied} postulées
                        </p>
                      </div>
                    </div>
                    <span
                      className={`text-[10px] font-light px-2 py-0.5 rounded-full ${
                        run.status === "completed"
                          ? "text-emerald-400 bg-emerald-400/10"
                          : run.status === "running"
                          ? "text-primary bg-primary/10"
                          : run.status === "failed"
                          ? "text-red-400 bg-red-400/10"
                          : "text-zinc-400 bg-zinc-400/10"
                      }`}
                    >
                      {run.status}
                    </span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {/* Documents section */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.55 }}
            className="rounded-2xl border border-border/15 bg-card/20 backdrop-blur-sm p-4"
          >
            <p className="text-xs font-light text-muted-foreground tracking-wide uppercase mb-3">
              Documents générés
            </p>
            <p className="text-xs text-muted-foreground/50 font-light">
              Les CV et lettres de motivation personnalisés apparaissent ici après exécution du pipeline.
              Téléchargez-les depuis les détails de chaque offre.
            </p>
            <div className="mt-3 flex gap-2">
              <Link
                to="/chat"
                className="inline-flex items-center gap-1.5 text-xs font-light px-3 py-1.5 rounded-full border border-border/20 text-muted-foreground hover:text-foreground hover:border-border/40 transition-all"
              >
                <MessageCircle className="w-3.5 h-3.5" />
                Parler au consultant
              </Link>
            </div>
          </motion.div>

        </div>
      </div>
      <BubbleNav />
    </div>
  );
};

export default Dashboard;
