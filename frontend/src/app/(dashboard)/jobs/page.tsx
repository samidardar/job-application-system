"use client";

import { useEffect, useState } from "react";
import { jobsApi } from "@/lib/api";
import { toast } from "sonner";
import { cn, getScoreClass, PLATFORM_LABELS, CONTRACT_LABELS, timeAgo } from "@/lib/utils";
import { ExternalLink, Filter, ChevronRight } from "lucide-react";
import { useRouter } from "next/navigation";

interface Job {
  id: string;
  title: string;
  company: string;
  platform: string;
  location: string | null;
  job_type: string | null;
  match_score: number | null;
  status: string;
  posted_at: string | null;
  scraped_at: string;
}

const STATUS_FILTER_OPTIONS = [
  { value: "", label: "Tous" },
  { value: "matched", label: "Matchées" },
  { value: "applied", label: "Soumises" },
  { value: "below_threshold", label: "Sous le seuil" },
];

export default function JobsPage() {
  const router = useRouter();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [scoreMin, setScoreMin] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {};
      if (statusFilter) params.status = statusFilter;
      if (scoreMin) params.score_min = parseInt(scoreMin);
      const res = await jobsApi.list(params);
      setJobs(res.data);
    } catch {
      toast.error("Erreur lors du chargement des offres");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [statusFilter, scoreMin]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-postulio-blue">Offres d'emploi</h1>
          <p className="text-muted-foreground text-sm mt-1">{jobs.length} offre(s) trouvée(s)</p>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border p-4 flex items-center gap-4">
        <Filter className="h-4 w-4 text-muted-foreground" />
        <div className="flex gap-3 flex-wrap">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="text-sm border rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-postulio-teal"
          >
            {STATUS_FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <select
            value={scoreMin}
            onChange={(e) => setScoreMin(e.target.value)}
            className="text-sm border rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-postulio-teal"
          >
            <option value="">Score minimum</option>
            <option value="85">85+</option>
            <option value="70">70+</option>
            <option value="50">50+</option>
          </select>
        </div>
      </div>

      {/* Jobs table */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-muted-foreground">Chargement...</div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Offre</th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Plateforme</th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Type</th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Score</th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Publié</th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Statut</th>
                <th className="w-8"></th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {jobs.map((job) => (
                <tr
                  key={job.id}
                  className="hover:bg-gray-50 transition cursor-pointer"
                  onClick={() => router.push(`/jobs/${job.id}`)}
                >
                  <td className="px-5 py-3">
                    <div className="font-medium text-sm">{job.title}</div>
                    <div className="text-xs text-muted-foreground">{job.company} · {job.location}</div>
                  </td>
                  <td className="px-5 py-3 text-sm text-muted-foreground">
                    {PLATFORM_LABELS[job.platform] || job.platform}
                  </td>
                  <td className="px-5 py-3 text-sm text-muted-foreground">
                    {job.job_type ? CONTRACT_LABELS[job.job_type] || job.job_type : "—"}
                  </td>
                  <td className="px-5 py-3">
                    {job.match_score !== null ? (
                      <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", getScoreClass(job.match_score))}>
                        {job.match_score}%
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-xs text-muted-foreground">
                    {timeAgo(job.posted_at || job.scraped_at)}
                  </td>
                  <td className="px-5 py-3">
                    <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">
                      {job.status}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-center py-10 text-muted-foreground text-sm">
                    Aucune offre. Lancez le pipeline pour commencer le scraping.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
