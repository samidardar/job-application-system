import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { ArrowLeft, Sparkles, BadgeEuro, Target, TrendingUp } from "lucide-react";
import VideoBackground from "@/components/VideoBackground";
import FloatingP from "@/components/FloatingP";
import BubbleNav from "@/components/BubbleNav";
import logo from "@/assets/logo.png";

const TARIF_PREMIER_MOIS = 8;
const TARIF_MENSUEL = 10;
const candidaturesSansPostulio = 100;
const candidaturesAvecPostulio = 1000;
const tauxReponse = 0.03;
const tauxConversion = 0.1;

const entretiensSansPostulio = candidaturesSansPostulio * tauxReponse;
const entretiensAvecPostulio = candidaturesAvecPostulio * tauxReponse;
const embauchesSansPostulio = entretiensSansPostulio * tauxConversion;
const embauchesAvecPostulio = entretiensAvecPostulio * tauxConversion;
const multiplicateur = embauchesAvecPostulio / embauchesSansPostulio;
const coutParEntretien = TARIF_MENSUEL / entretiensAvecPostulio;

const Pricing = () => {
  return (
    <div className="h-screen flex flex-col relative overflow-hidden">
      <VideoBackground />
      <FloatingP />

      <header className="relative z-10 flex items-center justify-between px-5 py-4 border-b border-border/10 backdrop-blur-sm bg-background/20">
        <Link to="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="w-4 h-4" />
          <span className="text-xs font-light tracking-widest uppercase">Retour</span>
        </Link>
        <div className="flex items-center gap-2">
          <img src={logo} alt="Postulio" className="w-6 h-6" />
          <span className="text-xs font-medium tracking-[0.15em] uppercase text-foreground/70">Tarifs</span>
        </div>
        <Link to="/chat" className="text-xs font-light tracking-widest uppercase text-muted-foreground hover:text-foreground transition-colors">
          Consultant
        </Link>
      </header>

      <div className="flex-1" />

      <section className="relative z-10 px-6 md:px-12 pb-10 md:pb-14">
        <motion.div
          className="flex items-center gap-2 mb-4"
          initial={{ opacity: 0, x: -16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6 }}
        >
          <div className="w-10 h-px bg-primary/70" />
          <span className="text-xs font-light tracking-[0.2em] uppercase text-muted-foreground">Tarif unique · Accès illimité</span>
        </motion.div>

        <motion.h1
          className="text-[2rem] md:text-[3.2rem] lg:text-[3.8rem] font-extralight tracking-tight leading-[1.05] max-w-5xl"
          initial={{ opacity: 0, y: 24, filter: "blur(8px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
        >
          Les ATS filtrent plus vite que toi.
          <br />
          Pour <span className="text-primary">8€ le 1er mois</span>, puis <span className="text-primary">10€/mois</span>, tu passes à l'échelle.
        </motion.h1>

        <motion.p
          className="mt-4 text-sm md:text-base text-muted-foreground font-light max-w-2xl leading-relaxed"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.2 }}
        >
          En France, décrocher une alternance, un stage ou un CDI est devenu une guerre de volume. Postulio automatise les candidatures,
          personnalise ton CV + lettre de motivation et t’aide à viser 1 000 entreprises au lieu de 100.
        </motion.p>

        <motion.div
          className="mt-7 grid grid-cols-1 lg:grid-cols-3 gap-3 max-w-6xl"
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.35 }}
        >
          <article className="rounded-2xl border border-border/15 bg-card/30 backdrop-blur-sm p-5 lg:col-span-1">
            <div className="flex items-center gap-2 text-primary mb-2">
              <BadgeEuro className="w-4 h-4" />
              <span className="text-xs tracking-widest uppercase">Offre Postulio</span>
            </div>
             <p className="text-4xl font-extralight tabular">8€ <span className="text-lg text-muted-foreground">puis 10€/mois</span></p>
             <p className="text-xs text-muted-foreground mt-1">1er mois à 8€, sans limite de candidatures</p>
            <ul className="mt-4 space-y-2 text-xs text-foreground/80 font-light">
              <li>• Candidatures en volume intelligent</li>
              <li>• CV optimisé ATS à télécharger</li>
              <li>• Lettre de motivation générée</li>
              <li>• Mentorat via consultant IA</li>
            </ul>
          </article>

          <article className="rounded-2xl border border-border/15 bg-card/30 backdrop-blur-sm p-5 lg:col-span-2">
            <div className="flex items-center gap-2 text-primary mb-3">
              <Target className="w-4 h-4" />
              <span className="text-xs tracking-widest uppercase">Équation d’impact</span>
            </div>
            <div className="text-xs md:text-sm font-light text-foreground/85 leading-relaxed space-y-2">
              <p className="font-mono text-primary/90">
                Sans Postulio: {candidaturesSansPostulio} × {Math.round(tauxReponse * 100)}% × {Math.round(tauxConversion * 100)}% = {embauchesSansPostulio.toFixed(1)} embauche potentielle/mois
              </p>
              <p className="font-mono text-primary/90">
                Avec Postulio: {candidaturesAvecPostulio} × {Math.round(tauxReponse * 100)}% × {Math.round(tauxConversion * 100)}% = {embauchesAvecPostulio.toFixed(1)} embauches potentielles/mois
              </p>
              <p className="font-mono">
                Multiplicateur de chance = {embauchesAvecPostulio.toFixed(1)} / {embauchesSansPostulio.toFixed(1)} = x{multiplicateur.toFixed(0)}
              </p>
            </div>

            <div className="mt-4 pt-4 border-t border-border/10 flex flex-wrap gap-4 text-[11px] text-muted-foreground">
              <span className="inline-flex items-center gap-1.5"><TrendingUp className="w-3.5 h-3.5 text-primary" /> {entretiensAvecPostulio.toFixed(0)} entretiens potentiels/mois</span>
              <span>Coût par entretien potentiel: <strong className="text-foreground">{coutParEntretien.toFixed(2)}€</strong></span>
            </div>
          </article>
        </motion.div>

        <motion.div
          className="mt-6 flex flex-wrap items-center gap-3"
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.5 }}
        >
          <Link to="/chat" className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-primary text-primary-foreground text-sm font-medium tracking-wide hover:brightness-110 transition-all">
            <Sparkles className="w-4 h-4" />
            Commencer pour 8€
          </Link>
          <Link to="/dashboard" className="px-6 py-3 rounded-full border border-border/20 text-sm font-light text-foreground/80 hover:text-foreground hover:border-border/40 transition-colors">
            Voir le dashboard
          </Link>
        </motion.div>
      </section>

      <BubbleNav />
    </div>
  );
};

export default Pricing;