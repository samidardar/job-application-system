import { useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, FileText, Check, ChevronRight, Briefcase, MapPin } from "lucide-react";
import { cv, ApiError } from "@/lib/api";

type ContractType = "alternance" | "stage" | "cdi";

interface OnboardingData {
  cvFile: File | null;
  cvUploaded: boolean;
  jobTitle: string;
  contractType: ContractType | null;
  city: string;
}

interface OnboardingSectionProps {
  onComplete?: (data: OnboardingData) => void;
}

const CONTRACT_OPTIONS: { value: ContractType; label: string; desc: string }[] = [
  { value: "alternance", label: "Alternance", desc: "Contrat pro ou apprentissage" },
  { value: "stage", label: "Stage", desc: "Stage conventionné" },
  { value: "cdi", label: "CDI", desc: "Contrat à durée indéterminée" },
];

const OnboardingSection = ({ onComplete }: OnboardingSectionProps) => {
  const [data, setData] = useState<OnboardingData>({
    cvFile: null,
    cvUploaded: false,
    jobTitle: "",
    contractType: null,
    city: "",
  });
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    const allowed = [
      "application/pdf",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ];
    if (!allowed.includes(file.type)) {
      setUploadError("Format accepté : PDF ou Word (.doc, .docx)");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadError("Le fichier ne doit pas dépasser 10 Mo");
      return;
    }

    setUploadError(null);
    setUploading(true);
    try {
      await cv.upload(file);
      setData((prev) => ({ ...prev, cvFile: file, cvUploaded: true }));
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Échec de l'import. Réessayez.");
    } finally {
      setUploading(false);
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      const file = e.dataTransfer.files[0];
      if (file) void handleFile(file);
    },
    [handleFile],
  );

  const isReady = data.cvUploaded && data.jobTitle.trim().length > 0 && data.contractType !== null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6 }}
      className="rounded-2xl border border-primary/20 bg-card/25 backdrop-blur-sm overflow-hidden"
    >
      {/* Header */}
      <div className="px-5 py-4 border-b border-border/10 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-primary/15 flex items-center justify-center">
          <Upload className="w-4 h-4 text-primary" />
        </div>
        <div>
          <p className="text-sm font-light text-foreground/90">Première étape</p>
          <p className="text-[10px] text-muted-foreground font-light">
            Importe ton CV, choisis ton poste et ton type de contrat
          </p>
        </div>
      </div>

      <div className="p-5 space-y-5">
        {/* CV Upload */}
        <div>
          <label className="text-[11px] font-light text-muted-foreground tracking-wide uppercase mb-2 block">
            Ton CV
          </label>
          {data.cvUploaded ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex items-center gap-3 px-4 py-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5"
            >
              <Check className="w-4 h-4 text-emerald-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-light text-foreground/90 truncate">
                  {data.cvFile?.name}
                </p>
                <p className="text-[10px] text-emerald-400/70 font-light">CV importé avec succès</p>
              </div>
              <button
                onClick={() => {
                  setData((prev) => ({ ...prev, cvFile: null, cvUploaded: false }));
                  setUploadError(null);
                }}
                className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
              >
                Changer
              </button>
            </motion.div>
          ) : (
            <>
              <div
                onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                onDragLeave={() => setDragActive(false)}
                onDrop={onDrop}
                onClick={() => fileRef.current?.click()}
                className={`cursor-pointer rounded-xl border-2 border-dashed transition-all duration-300 px-4 py-8 flex flex-col items-center gap-2 ${
                  dragActive
                    ? "border-primary/50 bg-primary/5"
                    : "border-border/20 bg-background/20 hover:border-border/40"
                } ${uploading ? "pointer-events-none opacity-50" : ""}`}
              >
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf,.doc,.docx"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void handleFile(f);
                  }}
                />
                {uploading ? (
                  <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                ) : (
                  <FileText className="w-6 h-6 text-muted-foreground/50" />
                )}
                <p className="text-xs font-light text-muted-foreground text-center">
                  {uploading
                    ? "Import en cours…"
                    : "Glisse ton CV ici ou clique pour sélectionner"}
                </p>
                <p className="text-[10px] text-muted-foreground/40 font-light">PDF, DOC, DOCX · max 10 Mo</p>
              </div>
              {uploadError && (
                <p className="mt-2 text-[11px] text-red-400 font-light">{uploadError}</p>
              )}
            </>
          )}
        </div>

        {/* Job title + City */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-[11px] font-light text-muted-foreground tracking-wide uppercase mb-2 block">
              Poste recherché
            </label>
            <div className="relative">
              <Briefcase className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/40" />
              <input
                type="text"
                value={data.jobTitle}
                onChange={(e) => setData((prev) => ({ ...prev, jobTitle: e.target.value }))}
                placeholder="ex. Développeur Full-Stack"
                className="w-full bg-background/30 text-foreground placeholder:text-muted-foreground/40 text-sm font-light pl-9 pr-4 py-3 rounded-xl border border-border/20 focus:outline-none focus:border-primary/40 transition-colors"
              />
            </div>
          </div>
          <div>
            <label className="text-[11px] font-light text-muted-foreground tracking-wide uppercase mb-2 block">
              Ville / Région
            </label>
            <div className="relative">
              <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/40" />
              <input
                type="text"
                value={data.city}
                onChange={(e) => setData((prev) => ({ ...prev, city: e.target.value }))}
                placeholder="ex. Paris, Lyon, Remote"
                className="w-full bg-background/30 text-foreground placeholder:text-muted-foreground/40 text-sm font-light pl-9 pr-4 py-3 rounded-xl border border-border/20 focus:outline-none focus:border-primary/40 transition-colors"
              />
            </div>
          </div>
        </div>

        {/* Contract type */}
        <div>
          <label className="text-[11px] font-light text-muted-foreground tracking-wide uppercase mb-2 block">
            Type de contrat
          </label>
          <div className="grid grid-cols-3 gap-2">
            {CONTRACT_OPTIONS.map((opt) => {
              const selected = data.contractType === opt.value;
              return (
                <button
                  key={opt.value}
                  onClick={() => setData((prev) => ({ ...prev, contractType: opt.value }))}
                  className={`relative rounded-xl border px-3 py-3 text-left transition-all duration-300 ${
                    selected
                      ? "border-primary/40 bg-primary/10"
                      : "border-border/15 bg-background/20 hover:border-border/30"
                  }`}
                >
                  <p className={`text-xs font-light ${selected ? "text-primary" : "text-foreground/80"}`}>
                    {opt.label}
                  </p>
                  <p className="text-[9px] text-muted-foreground/50 font-light mt-0.5">{opt.desc}</p>
                  {selected && (
                    <motion.div
                      layoutId="contract-check"
                      className="absolute top-2 right-2 w-4 h-4 rounded-full bg-primary/20 flex items-center justify-center"
                    >
                      <Check className="w-2.5 h-2.5 text-primary" />
                    </motion.div>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Submit */}
        <AnimatePresence>
          {isReady && (
            <motion.button
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              onClick={() => onComplete?.(data)}
              className="w-full flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-primary text-primary-foreground text-sm font-light tracking-wide hover:brightness-110 transition-all duration-300 active:scale-[0.98]"
            >
              Lancer la recherche
              <ChevronRight className="w-4 h-4" />
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};

export default OnboardingSection;
