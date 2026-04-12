import { motion } from "framer-motion";

const stats = [
  { value: "10×", label: "plus de candidatures" },
  { value: "1 000+", label: "entreprises ciblées" },
  { value: "< 2 min", label: "pour postuler" },
  { value: "87%", label: "de satisfaction" },
];

const StatsSection = () => {
  return (
    <section className="py-16 md:py-24 px-6">
      <div className="max-w-5xl mx-auto">
        <motion.div
          className="grid grid-cols-2 md:grid-cols-4 gap-px bg-border/30 rounded-2xl overflow-hidden border border-border/30"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.3 }}
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.1 } },
          }}
        >
          {stats.map((stat) => (
            <motion.div
              key={stat.label}
              className="bg-background p-8 md:p-10 text-center"
              variants={{
                hidden: { opacity: 0, scale: 0.95 },
                visible: {
                  opacity: 1,
                  scale: 1,
                  transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] },
                },
              }}
            >
              <div className="text-2xl md:text-3xl font-light text-gradient tabular tracking-tight">
                {stat.value}
              </div>
              <div className="mt-2 text-xs text-muted-foreground tracking-wide uppercase font-medium">
                {stat.label}
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
};

export default StatsSection;
