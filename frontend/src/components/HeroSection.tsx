import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import logo from "@/assets/logo.png";
import { useIsMobile } from "@/hooks/use-mobile";

const VIDEO_VERSION = "20260326-hd";

const HeroSection = () => {
  const isMobile = useIsMobile();
  const videoSrc = isMobile
    ? `/videos/hero-bg-mobile.mp4?v=${VIDEO_VERSION}`
    : `/videos/hero-bg-desktop.mp4?v=${VIDEO_VERSION}`;

  return (
    <section className="relative h-screen flex flex-col overflow-hidden">
      {/* Video Background */}
      <video
        key={videoSrc}
        autoPlay
        muted
        loop
        playsInline
        preload="auto"
        className="absolute inset-0 w-full h-full object-cover [transform:translateZ(0)]"
        style={{
          imageRendering: "auto",
          WebkitBackfaceVisibility: "hidden",
          backfaceVisibility: "hidden",
        }}
        src={videoSrc}
      />

      {/* Gradient overlays — top subtle, bottom strong for text */}
      <div className="absolute inset-0 bg-gradient-to-b from-background/20 via-transparent to-background/70 pointer-events-none" />
      <div className="absolute bottom-0 left-0 right-0 h-[55%] bg-gradient-to-t from-background/80 via-background/35 to-transparent pointer-events-none" />

      {/* Logo — top left */}
      <motion.div
        className="relative z-10 p-6 md:p-10 flex items-center gap-3"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.2, delay: 0.1 }}
      >
        <img src={logo} alt="Postulio" className="w-8 h-8 md:w-10 md:h-10" />
        <span className="text-sm font-medium tracking-widest uppercase text-foreground/60">
          Postulio
        </span>
      </motion.div>

      {/* Empty middle */}
      <div className="flex-1" />

      {/* Bottom content */}
      <div className="relative z-10 px-6 md:px-12 pb-14 md:pb-20 max-w-4xl">
        {/* Eyebrow */}
        <motion.div
          className="flex items-center gap-3 mb-6"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.8, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="reveal-line w-10 h-px" />
          <span className="text-xs font-medium tracking-[0.2em] uppercase text-muted-foreground">
            Alternance · Stage · CDI
          </span>
        </motion.div>

        {/* Headline — thin & large */}
        <motion.h1
          className="text-[2rem] md:text-[3.2rem] lg:text-[4rem] font-extralight tracking-tight leading-[1.1] text-balance"
          style={{ lineHeight: 1.1 }}
          initial={{ opacity: 0, y: 30, filter: "blur(10px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 1, delay: 0.5, ease: [0.16, 1, 0.3, 1] }}
        >
          Trouver un emploi
          <br />
          en France,{" "}
          <span className="font-medium text-gradient">c'est la galère.</span>
        </motion.h1>

        {/* Subtext */}
        <motion.p
          className="mt-5 text-sm md:text-base text-muted-foreground max-w-md leading-relaxed font-light"
          initial={{ opacity: 0, y: 20, filter: "blur(6px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.8, delay: 0.75, ease: [0.16, 1, 0.3, 1] }}
        >
          Des centaines de candidatures. Zéro réponse. On connaît.
          <br className="hidden md:block" />
          Postulio postule pour vous — à 1 000 entreprises au lieu de 100.
        </motion.p>

        {/* CTA */}
        <motion.div
          className="mt-8 flex items-center gap-4"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 1, ease: [0.16, 1, 0.3, 1] }}
        >
          <Link to="/chat" className="px-6 py-3 bg-primary text-primary-foreground font-medium rounded-full text-sm tracking-wide transition-all duration-300 hover:brightness-110 hover:shadow-[0_0_40px_-8px_hsl(220_100%_56%/0.4)] active:scale-[0.97]">
            Commencer gratuitement
          </Link>
          <Link to="/dashboard" className="px-6 py-3 text-foreground/60 font-light text-sm tracking-wide transition-colors duration-300 hover:text-foreground group flex items-center gap-2">
            Mon dashboard
            <svg className="w-4 h-4 transition-transform duration-300 group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 8.25L21 12m0 0l-3.75 3.75M21 12H3" />
            </svg>
          </Link>
        </motion.div>
      </div>
    </section>
  );
};

export default HeroSection;
