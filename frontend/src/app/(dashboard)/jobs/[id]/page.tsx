"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { jobsApi, documentsApi } from "@/lib/api";
import { toast } from "sonner";
import { cn, getScoreClass, PLATFORM_LABELS, CONTRACT_LABELS, timeAgo } from "@/lib/utils";
import {
  ArrowLeft, ExternalLink, FileText, Download,
  Sparkles, Building2, MapPin, Calendar, BadgeCheck, Loader2,
} from "lucide-react";

interface DocumentRef {
  id: string;
  document_type: "cv_tailored" | "cover_letter" | "cv_original";
  file_name: string | null;
  file_size_bytes: number | null;
  generated_at: string;
}

interface Job {
  id: string;
  platform: string;
  title: string;
  company: string;
  location: string | null;
  job_type: string | null;
  salary_range: string | null;
  description_clean: string | null;
  application_url: string | null;
  posted_at: string | null;
  scraped_at: string;
  match_score: number | null;
  match_rationale: { top_match_reasons?: string[]; skill_gaps?: string[] } | null;
  match_highlights: string[] | null;
  ats_keywords_critical: string[] | null;
  status: string;
  documents: DocumentRef[];
}

const STATUS_LABELS: Record<string, string> = {
  scraped: "Scrapé", matched: "Matché", cv_generated: "CV généré",
  letter_generated: "Lettre générée", ready_to_apply: "Prêt",
  applied: "Candidature envoyée", below_threshold: "Sous le seuil", failed: "Erreur",
};

const STATUS_COLORS: Record<string, string> = {
  scraped: "bg-gray-100 text-gray-700", matched: "bg-blue-100 text-blue-700",
  cv_generated: "bg-purple-100 text-purple-700", letter_generated: "bg-teal-100 text-teal-700",
  ready_to_apply: "bg-emerald-100 text-emerald-700", applied: "bg-green-100 text-green-700",
  below_threshold: "bg-orange-100 text-orange-700", failed: "bg-red-100 text-red-700",
};

export default function JobDetailPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = params.id as string;
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [preview, setPreview] = useState<{ type: string; html: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await jobsApi.get(jobId);
      setJob(res.data);
    } catch {
      toast.error("Offre introuvable");
      router.push("/jobs");
    } finally {
      setLoading(false);
    }
  }, [jobId, router]);

  useEffect(() => { load(); }, [load]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await jobsApi.generateDocuments(jobId);
      toast.success("Génération en cours…");
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        const res = await jobsApi.get(jobId);
        if (res.data.documents.length > 0 || attempts > 30) {
          clearInterval(poll);
          setJob(res.data);
          if (res.data.documents.length > 0) toast.success("CV ciblé et lettre générés !");
          setGenerating(false);
        }
      }, 3000);
    } catch {
      toast.error("Erreur lors de la génération");
      setGenerating(false);
    }
  };

  const openPreview = async (doc: DocumentRef) => {
    try {
      const res = await documentsApi.getPreview(doc.id);
      setPreview({ type: doc.document_type, html: res.data.content_html });
    } catch {
      toast.error("Impossible de charger l'aperçu");
    }
  };

  const cvDoc = job?.documents.find((d) => d.document_type === "cv_tailored");
  const letterDoc = job?.documents.find((d) => d.document_type === "cover_letter");

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="h-6 w-6 animate-spin text-postulio-teal" />
    </div>
  );

  if (!job) return null;

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Back */}
      <button onClick={() => router.push("/jobs")}
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-postulio-blue transition">
        <ArrowLeft className="h-4 w-4" /> Retour aux offres
      </button>

      {/* Header card */}
      <div className="bg-white rounded-xl border shadow-sm p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
                {PLATFORM_LABELS[job.platform] || job.platform}
              </span>
              <span className="text-muted-foreground">·</span>
              <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium",
                STATUS_COLORS[job.status] || "bg-gray-100 text-gray-700")}>
                {STATUS_LABELS[job.status] || job.status}
              </span>
            </div>
            <h1 className="text-2xl font-bold text-postulio-blue">{job.title}</h1>
            <div className="flex flex-wrap items-center gap-4 mt-2 text-sm text-muted-foreground">
              <span className="flex items-center gap-1.5"><Building2 className="h-4 w-4" />{job.company}</span>
              {job.location && <span className="flex items-center gap-1.5"><MapPin className="h-4 w-4" />{job.location}</span>}
              {job.job_type && <span className="flex items-center gap-1.5"><BadgeCheck className="h-4 w-4" />{CONTRACT_LABELS[job.job_type] || job.job_type}</span>}
              {job.posted_at && <span className="flex items-center gap-1.5"><Calendar className="h-4 w-4" />Publié {timeAgo(job.posted_at)}</span>}
              {job.salary_range && <span className="font-medium text-postulio-blue">{job.salary_range}</span>}
            </div>
          </div>
          <div className="flex flex-col items-end gap-3 shrink-0">
            {job.match_score !== null && (
              <div className="text-center">
                <div className={cn("text-2xl font-bold px-4 py-2 rounded-xl", getScoreClass(job.match_score))}>
                  {job.match_score}%
                </div>
                <div className="text-xs text-muted-foreground mt-1">Match</div>
              </div>
            )}
            {job.application_url && (
              <a href={job.application_url} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-2 bg-postulio-blue text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-900 transition">
                <ExternalLink className="h-4 w-4" /> Postuler
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Documents */}
      <div className="bg-white rounded-xl border shadow-sm p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-postulio-blue flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-postulio-teal" /> Documents personnalisés
          </h2>
          {job.documents.length === 0 && (
            <button onClick={handleGenerate} disabled={generating}
              className="flex items-center gap-2 bg-postulio-teal text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-teal-700 transition disabled:opacity-60">
              {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {generating ? "Génération en cours…" : "Générer CV ciblé + Lettre"}
            </button>
          )}
        </div>
        {job.documents.length === 0 ? (
          <div className="text-center py-10 text-muted-foreground border-2 border-dashed rounded-xl">
            <FileText className="h-8 w-8 mx-auto mb-2 opacity-30" />
            <p className="text-sm">Aucun document généré pour cette offre.</p>
            <p className="text-xs mt-1">Cliquez sur Générer pour créer votre CV ciblé et lettre de motivation.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {cvDoc && <DocCard doc={cvDoc} label="CV Ciblé" desc="Même format que votre CV, contenu optimisé pour ce poste" onPreview={() => openPreview(cvDoc)} />}
            {letterDoc && <DocCard doc={letterDoc} label="Lettre de motivation" desc="Rédigée en français, adaptée à l'offre et à l'entreprise" onPreview={() => openPreview(letterDoc)} />}
          </div>
        )}
      </div>

      {/* Match analysis */}
      {job.match_rationale && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {(job.match_highlights || job.match_rationale.top_match_reasons || []).length > 0 && (
            <div className="bg-white rounded-xl border shadow-sm p-5">
              <h3 className="font-semibold text-sm text-emerald-700 mb-3">Points forts</h3>
              <ul className="space-y-1.5">
                {(job.match_highlights || job.match_rationale.top_match_reasons || []).map((r: string, i: number) => (
                  <li key={i} className="text-sm flex gap-2"><span className="text-emerald-500 shrink-0">✓</span>{r}</li>
                ))}
              </ul>
            </div>
          )}
          {(job.match_rationale.skill_gaps || []).length > 0 && (
            <div className="bg-white rounded-xl border shadow-sm p-5">
              <h3 className="font-semibold text-sm text-orange-700 mb-3">Points d'attention</h3>
              <ul className="space-y-1.5">
                {job.match_rationale.skill_gaps!.map((g: string, i: number) => (
                  <li key={i} className="text-sm flex gap-2"><span className="text-orange-400 shrink-0">△</span>{g}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* ATS Keywords */}
      {(job.ats_keywords_critical || []).length > 0 && (
        <div className="bg-white rounded-xl border shadow-sm p-5">
          <h3 className="font-semibold text-sm text-postulio-blue mb-3">Mots-clés ATS critiques</h3>
          <div className="flex flex-wrap gap-2">
            {job.ats_keywords_critical!.map((kw: string) => (
              <span key={kw} className="text-xs bg-postulio-teal/10 text-postulio-teal px-2 py-1 rounded-full font-medium border border-postulio-teal/20">{kw}</span>
            ))}
          </div>
        </div>
      )}

      {/* Description */}
      {job.description_clean && (
        <div className="bg-white rounded-xl border shadow-sm p-6">
          <h3 className="font-semibold text-postulio-blue mb-3">Description du poste</h3>
          <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans leading-relaxed">{job.description_clean}</pre>
        </div>
      )}

      {/* Preview modal */}
      {preview && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setPreview(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b">
              <h3 className="font-semibold text-postulio-blue">
                {preview.type === "cv_tailored" ? "Aperçu — CV Ciblé" : "Aperçu — Lettre de motivation"}
              </h3>
              <button onClick={() => setPreview(null)} className="text-muted-foreground hover:text-postulio-blue text-xl">×</button>
            </div>
            <div className="overflow-auto flex-1 p-2">
              <iframe srcDoc={preview.html} className="w-full min-h-[600px] border-0" title="preview" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DocCard({ doc, label, desc, onPreview }: {
  doc: DocumentRef; label: string; desc: string; onPreview: () => void;
}) {
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const downloadUrl = `${apiBase}/api/v1/documents/${doc.id}/download`;
  const sizeKb = doc.file_size_bytes ? Math.round(doc.file_size_bytes / 1024) : null;
  return (
    <div className="border rounded-xl p-5 flex flex-col gap-3 hover:border-postulio-teal/50 transition">
      <div className="flex items-start gap-3">
        <div className="p-2.5 rounded-lg bg-postulio-teal/10 shrink-0">
          <FileText className="h-5 w-5 text-postulio-teal" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm text-postulio-blue">{label}</div>
          <div className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{desc}</div>
          {sizeKb && <div className="text-xs text-muted-foreground mt-1">{sizeKb} Ko · PDF</div>}
        </div>
      </div>
      <div className="flex gap-2">
        <button onClick={onPreview}
          className="flex-1 text-xs border border-postulio-teal/30 text-postulio-teal rounded-lg py-2 hover:bg-postulio-teal/5 transition font-medium">
          Aperçu
        </button>
        <a href={downloadUrl} download
          className="flex-1 flex items-center justify-center gap-1.5 text-xs bg-postulio-teal text-white rounded-lg py-2 hover:bg-teal-700 transition font-medium">
          <Download className="h-3.5 w-3.5" /> Télécharger PDF
        </a>
      </div>
    </div>
  );
}
