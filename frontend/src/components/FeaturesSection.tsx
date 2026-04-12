import { motion } from "framer-motion";
import { Bot, FileText, Rocket, LayoutDashboard } from "lucide-react";

const features = [
  {
    icon: Bot,
    title: "Votre consultant, pas un chatbot",
    description:
      "Il analyse votre profil, comprend vos ambitions et construit une vraie stratégie. Disponible 24h/24.",
  },
  {
    icon: FileText,
    title: "CV & lettres sur mesure",
    description:
      "Uploadez votre CV une fois. L'IA génère des lettres adaptées à chaque offre. Téléchargez, envoyez.",
  },
  {
    icon: LayoutDashboard,
    title: "Un seul dashboard",
    description:
      "Offres, entreprises, statuts, CV, lettres — tout centralisé. Fini les 15 onglets.",
  },
  {
    icon: Rocket,
    title: "×10 vos chances",
    description:
      "1 000 candidatures au lieu de 100. Vos chances sont multipliées. Mathématiquement.",
  },
];

const FeaturesSection = () => {
  return (
    <section className="py-16 md:py-28 px-6">
      <div className="max-w-5xl mx-auto">
        {/* Section header */}
        <motion.div
          className="mb-16 md:mb-20 max-w-2xl"
          initial={{ opacity: 0, y: 20, filter: "blur(6px)" }}
          whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="flex items-center gap-3 mb-5">
            <div className="reveal-line w-8 h-px" />
            <span className="text-xs font-medium tracking-[0.2em] uppercase text-muted-foreground">
              Fonctionnalités
            </span>
          </div>
          <h2 className="text-2xl md:text-[2.8rem] font-extralight tracking-tight leading-[1.15] text-balance">
            L'outil qu'on aurait voulu avoir{" "}
            <span className="text-muted-foreground">quand on galérait nous aussi.</span>
          </h2>
        </motion.div>

        {/* Feature grid */}
        <div className="grid md:grid-cols-2 gap-4 md:gap-5">
          {features.map((feature, i) => (
            <motion.div
              key={feature.title}
              className="group relative rounded-2xl border border-border/30 bg-card/30 p-7 md:p-9 transition-all duration-500 hover:border-primary/20 hover:bg-card/60"
              initial={{ opacity: 0, y: 24, filter: "blur(8px)" }}
              whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              viewport={{ once: true, amount: 0.2 }}
              transition={{ duration: 0.7, delay: i * 0.1, ease: [0.16, 1, 0.3, 1] }}
            >
              {/* Icon */}
              <div className="w-10 h-10 rounded-full border border-border/50 flex items-center justify-center mb-6 group-hover:border-primary/30 transition-colors duration-500">
                <feature.icon className="w-4 h-4 text-foreground/50 group-hover:text-primary transition-colors duration-500" strokeWidth={1.5} />
              </div>

              <h3 className="text-base font-medium mb-2 tracking-tight">{feature.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed font-light">{feature.description}</p>

              {/* Hover glow */}
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;
