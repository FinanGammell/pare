import React, { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";

export interface FeatureCardProps {
  icon: string;
  title: string;
  description: string;
  delay?: number;
}

/**
 * FeatureCard - Premium feature card with glassmorphism, hover effects, and cursor tracking
 */
export const FeatureCard: React.FC<FeatureCardProps> = ({
  icon,
  title,
  description,
  delay = 0,
}) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  const [isHovered, setIsHovered] = useState(false);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (cardRef.current) {
        const rect = cardRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        setMousePosition({ x, y });
      }
    };

    const card = cardRef.current;
    if (card) {
      card.addEventListener("mousemove", handleMouseMove);
      return () => {
        card.removeEventListener("mousemove", handleMouseMove);
      };
    }
  }, []);

  // Calculate tilt based on mouse position
  const tiltX = isHovered ? (mousePosition.y - 150) / 15 : 0;
  const tiltY = isHovered ? (150 - mousePosition.x) / 15 : 0;

  return (
    <motion.div
      ref={cardRef}
      className="feature-card"
      initial={{ opacity: 0, y: 30, scale: 0.9 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{
        duration: 0.6,
        delay,
        ease: [0.16, 1, 0.3, 1], // Custom easing for premium feel
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        transform: `perspective(1000px) rotateX(${tiltX}deg) rotateY(${tiltY}deg)`,
        transformStyle: "preserve-3d",
      }}
    >
      {/* Glow effect on hover */}
      <div
        className="feature-card-glow"
        style={{
          opacity: isHovered ? 0.6 : 0,
          transform: `translate(${mousePosition.x - 150}px, ${mousePosition.y - 150}px)`,
        }}
      />
      
      <div className="feature-card-content">
        <div className="feature-card-icon">{icon}</div>
        <h3 className="feature-card-title">{title}</h3>
        <p className="feature-card-description">{description}</p>
      </div>
    </motion.div>
  );
};

