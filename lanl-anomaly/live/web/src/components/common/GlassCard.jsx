import { motion } from "framer-motion";
import { cn } from "../../lib/utils";

export default function GlassCard({ children, className, onClick, ...props }) {
  return (
    <motion.div
      className={cn("panel panel-hover", className)}
      whileHover={{ y: -1 }}
      onClick={onClick}
      {...props}
    >
      {children}
    </motion.div>
  );
}
