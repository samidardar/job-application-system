"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    if (isAuthenticated()) {
      router.replace("/dashboard");
    } else {
      router.replace("/login");
    }
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-postulio-light">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-postulio-blue">Postulio</h1>
        <p className="text-muted-foreground mt-2">Chargement...</p>
      </div>
    </div>
  );
}
