import { useState } from "react";
import { auth, ApiError } from "@/lib/api";
import { useNavigate, Link } from "react-router-dom";
import VideoBackground from "@/components/VideoBackground";
import FloatingP from "@/components/FloatingP";
import logo from "@/assets/logo.png";

const Login = () => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await auth.login(email, password);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Connexion impossible. Veuillez réessayer.");
    } finally {
      setLoading(false);
    }
  };

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
            <h1 className="text-xl font-extralight text-foreground/90 text-center">Se connecter</h1>

            {error && (
              <p className="text-red-400 text-xs font-light text-center bg-red-900/20 border border-red-500/20 rounded-xl px-3 py-2">
                {error}
              </p>
            )}

            <div className="space-y-3">
              <input
                type="email"
                placeholder="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-background/30 text-foreground placeholder:text-muted-foreground/50 text-sm font-light px-4 py-3 rounded-xl border border-border/20 focus:outline-none focus:border-primary/40 transition-colors"
                required
                autoComplete="email"
              />
              <input
                type="password"
                placeholder="Mot de passe"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-background/30 text-foreground placeholder:text-muted-foreground/50 text-sm font-light px-4 py-3 rounded-xl border border-border/20 focus:outline-none focus:border-primary/40 transition-colors"
                required
                autoComplete="current-password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-primary text-primary-foreground text-sm font-light py-3 rounded-xl hover:brightness-110 disabled:opacity-50 transition-all duration-300"
            >
              {loading ? "Connexion…" : "Connexion"}
            </button>

            <p className="text-muted-foreground text-center text-xs font-light">
              Pas encore inscrit ?{" "}
              <Link to="/register" className="text-primary hover:underline">
                Créer un compte
              </Link>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Login;
