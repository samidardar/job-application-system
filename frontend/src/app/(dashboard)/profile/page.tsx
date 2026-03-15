"use client";

import { useEffect, useState, useRef } from "react";
import { usersApi, cvApi } from "@/lib/api";
import { toast } from "sonner";
import { Upload, CheckCircle, User, Settings } from "lucide-react";

interface Profile {
  phone: string | null;
  ville: string | null;
  linkedin_url: string | null;
  github_url: string | null;
  portfolio_url: string | null;
  cv_original_path: string | null;
  skills_technical: string[] | null;
  education: Array<{ degree: string; school: string; year_end?: string }> | null;
  experience: Array<{ title: string; company: string; duration?: string }> | null;
}

interface Preferences {
  target_roles: string[] | null;
  contract_types: string[] | null;
  preferred_locations: string[] | null;
  min_match_score: number;
  daily_application_limit: number;
  auto_apply_enabled: boolean;
  pipeline_enabled: boolean;
  pipeline_hour: number;
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [pRes, prRes] = await Promise.all([
          usersApi.getProfile(),
          usersApi.getPreferences(),
        ]);
        setProfile(pRes.data);
        setPrefs(prRes.data);
      } catch {
        toast.error("Erreur lors du chargement du profil");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const saveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profile) return;
    setSaving(true);
    try {
      await usersApi.updateProfile({
        phone: profile.phone,
        ville: profile.ville,
        linkedin_url: profile.linkedin_url,
        github_url: profile.github_url,
        portfolio_url: profile.portfolio_url,
      });
      toast.success("Profil sauvegardé !");
    } catch {
      toast.error("Erreur lors de la sauvegarde");
    } finally {
      setSaving(false);
    }
  };

  const savePrefs = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prefs) return;
    setSaving(true);
    try {
      await usersApi.updatePreferences(prefs as unknown as Record<string, unknown>);
      toast.success("Préférences sauvegardées !");
    } catch {
      toast.error("Erreur lors de la sauvegarde");
    } finally {
      setSaving(false);
    }
  };

  const uploadCV = async (file: File) => {
    setUploading(true);
    try {
      const res = await cvApi.upload(file);
      toast.success(`CV uploadé ! ${res.data.skills_count} compétences extraites.`);
      // Reload profile
      const pRes = await usersApi.getProfile();
      setProfile(pRes.data);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Erreur lors de l'upload");
    } finally {
      setUploading(false);
    }
  };

  if (loading) {
    return <div className="animate-pulse space-y-4"><div className="h-64 bg-gray-200 rounded-xl" /></div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-postulio-blue">Profil & CV</h1>
        <p className="text-muted-foreground text-sm mt-1">Configurez votre profil pour des candidatures optimales</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* CV Upload */}
        <div className="bg-white rounded-xl border p-6 shadow-sm">
          <h2 className="font-semibold text-postulio-blue mb-4 flex items-center gap-2">
            <Upload className="h-4 w-4" />
            Mon CV (PDF)
          </h2>

          {profile?.cv_original_path ? (
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 mb-4 flex items-center gap-3">
              <CheckCircle className="h-5 w-5 text-emerald-500 flex-shrink-0" />
              <div>
                <div className="text-sm font-medium text-emerald-700">CV uploadé et analysé</div>
                <div className="text-xs text-emerald-600 mt-0.5">
                  {profile.skills_technical?.length || 0} compétences •{" "}
                  {profile.experience?.length || 0} expériences •{" "}
                  {profile.education?.length || 0} formations
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
              <div className="text-sm text-amber-700">Aucun CV uploadé. Le pipeline ne peut pas démarrer sans CV.</div>
            </div>
          )}

          <div
            className="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer hover:border-postulio-teal transition-colors"
            onClick={() => fileRef.current?.click()}
          >
            <Upload className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
            <p className="text-sm font-medium text-postulio-blue">
              {uploading ? "Upload en cours..." : "Cliquer pour uploader votre CV"}
            </p>
            <p className="text-xs text-muted-foreground mt-1">PDF uniquement, max 10 Mo</p>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && uploadCV(e.target.files[0])}
          />

          {/* CV preview */}
          {profile?.skills_technical && profile.skills_technical.length > 0 && (
            <div className="mt-4">
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Compétences extraites</div>
              <div className="flex flex-wrap gap-1.5">
                {profile.skills_technical.slice(0, 15).map((skill) => (
                  <span key={skill} className="text-xs bg-postulio-light text-postulio-teal px-2 py-0.5 rounded-full border border-postulio-teal/20">
                    {skill}
                  </span>
                ))}
                {profile.skills_technical.length > 15 && (
                  <span className="text-xs text-muted-foreground">+{profile.skills_technical.length - 15} autres</span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Profile info */}
        <div className="bg-white rounded-xl border p-6 shadow-sm">
          <h2 className="font-semibold text-postulio-blue mb-4 flex items-center gap-2">
            <User className="h-4 w-4" />
            Informations personnelles
          </h2>
          <form onSubmit={saveProfile} className="space-y-3">
            {[
              { key: "phone", label: "Téléphone", type: "tel" },
              { key: "ville", label: "Ville", type: "text" },
              { key: "linkedin_url", label: "LinkedIn URL", type: "url" },
              { key: "github_url", label: "GitHub URL", type: "url" },
              { key: "portfolio_url", label: "Portfolio URL", type: "url" },
            ].map(({ key, label, type }) => (
              <div key={key}>
                <label className="block text-xs font-medium text-muted-foreground mb-1">{label}</label>
                <input
                  type={type}
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-postulio-teal"
                  value={(profile as any)?.[key] || ""}
                  onChange={(e) => setProfile({ ...profile!, [key]: e.target.value })}
                />
              </div>
            ))}
            <button
              type="submit"
              disabled={saving}
              className="w-full bg-postulio-teal text-white rounded-lg py-2 text-sm font-medium hover:bg-teal-700 transition disabled:opacity-60 mt-2"
            >
              {saving ? "Sauvegarde..." : "Sauvegarder le profil"}
            </button>
          </form>
        </div>

        {/* Job preferences */}
        <div className="lg:col-span-2 bg-white rounded-xl border p-6 shadow-sm">
          <h2 className="font-semibold text-postulio-blue mb-4 flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Préférences de recherche
          </h2>
          {prefs && (
            <form onSubmit={savePrefs} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">
                    Rôles cibles (un par ligne)
                  </label>
                  <textarea
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-postulio-teal h-28"
                    value={(prefs.target_roles || []).join("\n")}
                    onChange={(e) => setPrefs({ ...prefs, target_roles: e.target.value.split("\n").filter(Boolean) })}
                    placeholder="Data Scientist&#10;ML Engineer&#10;IA Engineer"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Types de contrat</label>
                  <div className="space-y-2 mt-1">
                    {["Alternance", "Stage", "CDI", "CDD"].map((ct) => (
                      <label key={ct} className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                          type="checkbox"
                          className="accent-postulio-teal"
                          checked={(prefs.contract_types || []).includes(ct)}
                          onChange={(e) => {
                            const types = prefs.contract_types || [];
                            setPrefs({
                              ...prefs,
                              contract_types: e.target.checked
                                ? [...types, ct]
                                : types.filter((t) => t !== ct),
                            });
                          }}
                        />
                        {ct}
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">
                    Villes préférées (une par ligne)
                  </label>
                  <textarea
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-postulio-teal h-28"
                    value={(prefs.preferred_locations || []).join("\n")}
                    onChange={(e) => setPrefs({ ...prefs, preferred_locations: e.target.value.split("\n").filter(Boolean) })}
                    placeholder="Paris, France&#10;Lyon, France&#10;Remote"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Score minimum</label>
                  <input
                    type="number" min={0} max={100}
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-postulio-teal"
                    value={prefs.min_match_score}
                    onChange={(e) => setPrefs({ ...prefs, min_match_score: parseInt(e.target.value) })}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Limite journalière</label>
                  <input
                    type="number" min={1} max={50}
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-postulio-teal"
                    value={prefs.daily_application_limit}
                    onChange={(e) => setPrefs({ ...prefs, daily_application_limit: parseInt(e.target.value) })}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Heure du pipeline</label>
                  <input
                    type="number" min={0} max={23}
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-postulio-teal"
                    value={prefs.pipeline_hour}
                    onChange={(e) => setPrefs({ ...prefs, pipeline_hour: parseInt(e.target.value) })}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <label className="flex items-center gap-2 text-sm cursor-pointer mt-4">
                    <input
                      type="checkbox"
                      className="accent-postulio-teal"
                      checked={prefs.auto_apply_enabled}
                      onChange={(e) => setPrefs({ ...prefs, auto_apply_enabled: e.target.checked })}
                    />
                    Soumission automatique
                  </label>
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      className="accent-postulio-teal"
                      checked={prefs.pipeline_enabled}
                      onChange={(e) => setPrefs({ ...prefs, pipeline_enabled: e.target.checked })}
                    />
                    Pipeline actif
                  </label>
                </div>
              </div>
              <button
                type="submit"
                disabled={saving}
                className="bg-postulio-teal text-white rounded-lg px-6 py-2 text-sm font-medium hover:bg-teal-700 transition disabled:opacity-60"
              >
                {saving ? "Sauvegarde..." : "Sauvegarder les préférences"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
