const FooterSection = () => {
  return (
    <footer className="py-10 px-6 border-t border-border/20">
      <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-muted-foreground font-light tracking-wide">
        <span>© 2026 Postulio</span>
        <div className="flex gap-6">
          <a href="#" className="hover:text-foreground transition-colors duration-300">Mentions légales</a>
          <a href="#" className="hover:text-foreground transition-colors duration-300">Confidentialité</a>
          <a href="#" className="hover:text-foreground transition-colors duration-300">Contact</a>
        </div>
      </div>
    </footer>
  );
};

export default FooterSection;
