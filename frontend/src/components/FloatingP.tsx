import { motion } from "framer-motion";
import pImage from "@/assets/p-floating.png";

const floatingPs = [
  { x: "10%", y: "15%", size: 120, delay: 0, duration: 18, rotate: 15 },
  { x: "75%", y: "10%", size: 80, delay: 2, duration: 22, rotate: -20 },
  { x: "85%", y: "55%", size: 140, delay: 1, duration: 20, rotate: 10 },
  { x: "20%", y: "65%", size: 60, delay: 3, duration: 16, rotate: -15 },
  { x: "50%", y: "30%", size: 200, delay: 0.5, duration: 24, rotate: 8 },
  { x: "35%", y: "80%", size: 90, delay: 1.5, duration: 19, rotate: -12 },
];

const FloatingP = () => {
  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
      {floatingPs.map((p, i) => (
        <motion.img
          key={i}
          src={pImage}
          alt=""
          className="absolute opacity-[0.04]"
          style={{
            left: p.x,
            top: p.y,
            width: p.size,
            height: p.size,
          }}
          animate={{
            y: [0, -30, 0, 20, 0],
            x: [0, 15, -10, 5, 0],
            rotate: [0, p.rotate, -p.rotate / 2, p.rotate / 3, 0],
            scale: [1, 1.05, 0.97, 1.02, 1],
          }}
          transition={{
            duration: p.duration,
            delay: p.delay,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
};

export default FloatingP;
