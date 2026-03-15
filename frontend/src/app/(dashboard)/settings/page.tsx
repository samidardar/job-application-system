"use client";

import { clearTokens } from "@/lib/auth";
import { useRouter } from "next/navigation";
import { LogOut, Info } from "lucide-react";

export default function SettingsPage() {
  const router = useRouter();

  const logout = () => {
    clearTokens();
    router.push("/login");
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-postulio-blue">Paramètres</h1>
        <p className="text-muted-foreground text-sm mt-1">Gérez votre compte Postulio</p>
      </div>

      <div className="bg-white rounded-xl border p-6 shadow-sm">
        <h2 className="font-semibold text-postulio-blue mb-4 flex items-center gap-2">
          <Info className="h-4 w-4" />
          À propos de Postulio
        </h2>
        <div className="space-y-2 text-sm text-muted-foreground">
          <p>Postulio est une plateforme IA d'automatisation de candidatures pour le marché français.</p>
          <p>Chaque matin à 8h00, le pipeline scrape les offres des 24 dernières heures sur LinkedIn, Indeed et Welcome to the Jungle, génère des documents personnalisés avec Claude et soumet vos candidatures automatiquement.</p>
          <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
            {[
              ["Backend", "FastAPI + Python 3.12"],
              ["IA", "Claude claude-sonnet-4-6"],
              ["Scraping", "jobspy + Playwright"],
              ["PDF", "WeasyPrint"],
              ["Queue", "Celery + Redis"],
              ["Base de données", "PostgreSQL"],
            ].map(([k, v]) => (
              <div key={k} className="bg-gray-50 rounded-lg p-2">
                <div className="font-medium text-postulio-blue">{k}</div>
                <div className="text-muted-foreground">{v}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl border p-6 shadow-sm">
        <h2 className="font-semibold text-red-600 mb-4 flex items-center gap-2">
          <LogOut className="h-4 w-4" />
          Déconnexion
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          Se déconnecter de votre session Postulio.
        </p>
        <button
          onClick={logout}
          className="bg-red-50 text-red-600 border border-red-200 rounded-lg px-4 py-2 text-sm font-medium hover:bg-red-100 transition"
        >
          Se déconnecter
        </button>
      </div>
    </div>
  );
}
