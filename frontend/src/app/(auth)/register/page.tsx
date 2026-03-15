"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { authApi } from "@/lib/api";
import { setTokens } from "@/lib/auth";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    password: "",
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await authApi.register(form);
      setTokens(res.data.access_token, res.data.refresh_token);
      toast.success("Compte créé ! Bienvenue sur Postulio.");
      router.push("/profile");
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Inscription échouée");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-postulio-light to-white flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-postulio-blue">Postulio</h1>
          <p className="text-muted-foreground mt-2">Commencez à postuler automatiquement</p>
        </div>

        <div className="bg-white rounded-2xl shadow-lg border p-8">
          <h2 className="text-xl font-semibold mb-6">Créer un compte</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1">Prénom</label>
                <input
                  type="text"
                  required
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-postulio-teal"
                  value={form.first_name}
                  onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Nom</label>
                <input
                  type="text"
                  required
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-postulio-teal"
                  value={form.last_name}
                  onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Email</label>
              <input
                type="email"
                required
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-postulio-teal"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Mot de passe</label>
              <input
                type="password"
                required
                minLength={8}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-postulio-teal"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-postulio-teal text-white rounded-lg py-2.5 font-medium hover:bg-teal-700 transition disabled:opacity-60"
            >
              {loading ? "Création..." : "Créer mon compte"}
            </button>
          </form>

          <p className="text-center text-sm text-muted-foreground mt-4">
            Déjà un compte ?{" "}
            <Link href="/login" className="text-postulio-teal font-medium hover:underline">
              Se connecter
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
