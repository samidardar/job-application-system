import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Home, MessageCircle, LayoutDashboard, BadgeEuro } from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";
import logo from "@/assets/logo.png";

const NAV_ITEMS = [
  { path: "/", icon: Home, label: "Accueil" },
  { path: "/chat", icon: MessageCircle, label: "Consultant" },
  { path: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { path: "/pricing", icon: BadgeEuro, label: "Tarifs" },
];

const BubbleNav = () => {
  const [isOpen, setIsOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col-reverse items-center gap-3">
      {/* Toggle button */}
      <motion.button
        onClick={() => setIsOpen((o) => !o)}
        className="w-14 h-14 rounded-full bg-card/60 border border-border/30 backdrop-blur-md flex items-center justify-center shadow-lg shadow-background/40 hover:border-primary/40 transition-colors"
        whileTap={{ scale: 0.9 }}
        animate={{ rotate: isOpen ? 135 : 0 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      >
        <img src={logo} alt="Menu" className="w-7 h-7" />
      </motion.button>

      {/* Nav items */}
      <AnimatePresence>
        {isOpen &&
          NAV_ITEMS.map((item, i) => {
            const isActive = location.pathname === item.path;
            return (
              <motion.button
                key={item.path}
                initial={{ opacity: 0, y: 20, scale: 0.6 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 10, scale: 0.6 }}
                transition={{
                  duration: 0.3,
                  delay: i * 0.06,
                  ease: [0.16, 1, 0.3, 1],
                }}
                onClick={() => {
                  navigate(item.path);
                  setIsOpen(false);
                }}
                className={`group relative w-12 h-12 rounded-full border backdrop-blur-md flex items-center justify-center transition-all duration-300 ${
                  isActive
                    ? "bg-primary/20 border-primary/40 shadow-[0_0_20px_-4px_hsl(220_100%_56%/0.3)]"
                    : "bg-card/50 border-border/20 hover:border-primary/30 hover:bg-card/70"
                }`}
              >
                <item.icon
                  className={`w-5 h-5 transition-colors ${
                    isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                  }`}
                />
                {/* Tooltip */}
                <span className="absolute right-full mr-3 px-2.5 py-1 rounded-lg bg-card/80 border border-border/20 backdrop-blur-md text-[10px] font-light text-foreground/80 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                  {item.label}
                </span>
              </motion.button>
            );
          })}
      </AnimatePresence>
    </div>
  );
};

export default BubbleNav;
