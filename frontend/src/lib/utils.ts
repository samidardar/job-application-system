import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function getScoreClass(score: number | null): string {
  if (!score) return "score-low";
  if (score >= 85) return "score-excellent";
  if (score >= 70) return "score-good";
  if (score >= 50) return "score-average";
  return "score-low";
}

export function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "—";
  const diff = Date.now() - new Date(dateStr).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 24) return `il y a ${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `il y a ${days}j`;
  return formatDate(dateStr);
}

export const STATUS_LABELS: Record<string, string> = {
  pending: "En attente",
  submitted: "Soumise",
  viewed: "Vue",
  rejected: "Refusée",
  interview_scheduled: "Entretien",
  offer_received: "Offre reçue",
};

export const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  submitted: "bg-blue-100 text-blue-700",
  viewed: "bg-purple-100 text-purple-700",
  rejected: "bg-red-100 text-red-700",
  interview_scheduled: "bg-emerald-100 text-emerald-700",
  offer_received: "bg-amber-100 text-amber-700",
};

export const PLATFORM_LABELS: Record<string, string> = {
  linkedin: "LinkedIn",
  indeed: "Indeed",
  welcometothejungle: "WTTJ",
};

export const CONTRACT_LABELS: Record<string, string> = {
  alternance: "Alternance",
  stage: "Stage",
  cdi: "CDI",
  cdd: "CDD",
  freelance: "Freelance",
};
