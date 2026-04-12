import { motion } from "framer-motion";

const steps = [
  {
    num: "01",
    title: "Déposez votre CV",
    desc: "Importez votre CV et dites-nous où vous cherchez. 30 secondes.",
  },
  {
    num: "02",
    title: "Parlez à votre consultant",
    desc: "Il vous pose les bonnes questions et prépare votre stratégie.",
  },
  {
    num: "03",
    title: "Postulez en masse",
    desc: "CV et LDM générés pour chaque offre. Cliquez, postulez. C'est tout.",
  },
];

const HowItWorksSection = () => {
  return (
    <section className="py-16 md:py-28 px-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <motion.div
          className="mb-16 md:mb-20"
          initial={{ opacity: 0, y: 16, filter: "blur(4px)" }}
          whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="flex items-center gap-3 mb-5">
            <div className="reveal-line w-8 h-px" />
            <span className="text-xs font-medium tracking-[0.2em] uppercase text-muted-foreground">
              Comment ça marche
            </span>
          </div>
          <h2 className="text-2xl md:text-[2.8rem] font-extralight tracking-tight leading-[1.15]">
            3 étapes. <span className="text-muted-foreground">C'est tout.</span>
          </h2>
        </motion.div>

        {/* Steps */}
        <div className="space-y-0">
          {steps.map((step, i) => (
            <motion.div
              key={step.num}
              className="group flex items-start gap-6 md:gap-10 py-8 md:py-10 border-t border-border/30 last:border-b"
              initial={{ opacity: 0, x: -20, filter: "blur(6px)" }}
              whileInView={{ opacity: 1, x: 0, filter: "blur(0px)" }}
              viewport={{ once: true, amount: 0.3 }}
              transition={{ duration: 0.7, delay: i * 0.1, ease: [0.16, 1, 0.3, 1] }}
            >
              <span className="text-3xl md:text-4xl font-extralight text-muted-foreground/30 tabular shrink-0 group-hover:text-primary/40 transition-colors duration-500">
                {step.num}
              </span>
              <div>
                <h3 className="text-lg md:text-xl font-medium tracking-tight mb-1 group-hover:text-primary transition-colors duration-500">
                  {step.title}
                </h3>
                <p className="text-sm text-muted-foreground font-light leading-relaxed max-w-md">
                  {step.desc}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default HowItWorksSection;
