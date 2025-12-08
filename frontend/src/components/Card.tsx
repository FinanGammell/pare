import React from "react";
import { motion } from "framer-motion";

export interface CardProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
  hover?: boolean;
  delay?: number;
}

/**
 * Card - Premium glassmorphic card component with hover effects
 */
export const Card: React.FC<CardProps> = ({
  children,
  className = "",
  onClick,
  hover = true,
  delay = 0,
}) => {
  return (
    <motion.div
      className={`glass-card ${className}`}
      onClick={onClick}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3, delay }}
      whileHover={hover ? { y: -3, transition: { duration: 0.25 } } : undefined}
    >
      {children}
    </motion.div>
  );
};

