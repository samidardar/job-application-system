import { useState } from "react";
import { auth, ApiError } from "@/lib/api";
import { useNavigate, Link } from "react-router-dom";
import VideoBackground from "@/components/VideoBackground";
import FloatingP from "@/components/FloatingP";
import logo from "@/assets/logo.png";

const Register = () => {
  const [form, setForm] = useState({
    email: "",
    password: "",
    first_name: "",
    last_name: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await auth.register(form.email, form.password, form.first_name, form.last_name);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Inscription impossible. Veuillez réessayer.");
    } finally {
      setLoading(false);
    }
  };

  const set = (field: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [field]: e.target.value }));

  return (
    <div className="min-h-screen flex flex-col relative overflow-hidden">
      <VideoBackground />
      <FloatingP />
      <div className="relative z-10 flex-1 flex items-center justify-center px-4">
        <div className="w-full max-w-md">
          <div className="flex items-center justify-center gap-2 mb-8">
            <img src={logo} alt="Postulio" className="w-8 h-8" />
            <span className="text-sm font-medium tracking-[0.2em] uppercase text-foreground/70">Postulio</span>
          </div>

          <form
            onSubmit={(e) => { void handleSubmit(e); }}
            className="rounded-2xl border border-border/15 bg-card/20 backdrop-blur-sm p-8 space-y-4"
          >
            <h1 className="text-xl font-extralight text-foreground/90 text-center">Créer un compte</h1>

            {error && (
              <p className="text-red-400 text-xs font-light text-center bg-red-900/20 border border-red-500/20 rounded-xl px-3 py-2">
                {error}
              </p>
            )}

            <div className="space-y-3">
              <div className="flex gap-3">
                <input
                  type="text"
                  placeholder="Prénom"
                  value={form.first_name}
                  onChange={set("first_name")}
                  className="flex-1 bg-background/30 text-foreground placeholder:text-muted-foreground/50 text-sm font-light px-4 py-3 rounded-xl border border-border/20 focus:outline-none focus:border-primary/40 transition-colors"
                  required
                  autoComplete="given-name"
                />
                <input
                  type="text"
                  placeholder="Nom"
                  value={form.last_name}
                  onChange={set("last_name")}
                  className="flex-1 bg-background/30 text-foreground placeholder:text-muted-foreground/50 text-sm font-light px-4 py-3 rounded-xl border border-border/20 focus:outline-none focus:border-primary/40 transition-colors"
                  required
                  autoComplete="family-name"
                />
              </div>
              <input
                type="email"
                placeholder="Email"
                value={form.email}
                onChange={set("email")}
                className="w-full bg-background/30 text-foreground placeholder:text-muted-foreground/50 text-sm font-light px-4 py-3 rounded-xl border border-border/20 focus:outline-none focus:border-primary/40 transition-colors"
                required
                autoComplete="email"
              />
              <input
                type="password"
                placeholder="Mot de passe (min 8 car., maj, min, chiffre)"
                value={form.password}
                onChange={set("password")}
                className="w-full bg-background/30 text-foreground placeholder:text-muted-foreground/50 text-sm font-light px-4 py-3 rounded-xl border border-border/20 focus:outline-none focus:border-primary/40 transition-colors"
                required
                autoComplete="new-password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-primary text-primary-foreground text-sm font-light py-3 rounded-xl hover:brightness-110 disabled:opacity-50 transition-all duration-300"
            >
              {loading ? "Inscription…" : "S'inscrire"}
            </button>

            <p className="text-muted-foreground text-center text-xs font-light">
              Déjà inscrit ?{" "}
              <Link to="/login" className="text-primary hover:underline">
                Se connecter
              </Link>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Register;
