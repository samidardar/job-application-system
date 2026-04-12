import { motion } from "framer-motion";

const CTASection = () => {
  return (
    <section className="py-20 md:py-32 px-6">
      <motion.div
        className="max-w-4xl mx-auto relative"
        initial={{ opacity: 0, y: 24, filter: "blur(8px)" }}
        whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        viewport={{ once: true, amount: 0.3 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
      >
        {/* CTA card */}
        <div className="relative rounded-3xl border border-border/30 bg-card/40 p-10 md:p-16 overflow-hidden">
          {/* Background glow */}
          <div className="absolute top-0 right-0 w-[300px] h-[300px] bg-primary/5 rounded-full blur-[120px] pointer-events-none" />

          <h2 className="text-2xl md:text-[2.8rem] font-extralight tracking-tight leading-[1.15] text-balance relative">
            Arrêtez de galérer.
            <br />
            <span className="text-gradient font-medium">Commencez à postuler.</span>
          </h2>
          <p className="mt-5 text-sm md:text-base text-muted-foreground font-light max-w-md leading-relaxed relative">
            Alternance, stage ou CDI — Postulio s'occupe de tout. Vous, vous vous concentrez sur les entretiens.
          </p>
          <motion.div
            className="mt-8 relative"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.3 }}
          >
            <button className="px-6 py-3 bg-primary text-primary-foreground font-medium rounded-full text-sm tracking-wide transition-all duration-300 hover:brightness-110 hover:shadow-[0_0_40px_-8px_hsl(220_100%_56%/0.4)] active:scale-[0.97]">
              Lancer Postulio
            </button>
          </motion.div>
        </div>
      </motion.div>
    </section>
  );
};

export default CTASection;
