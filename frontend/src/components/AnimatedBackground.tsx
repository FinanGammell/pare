import React, { useEffect, useRef, useState } from "react";
import { Starfield } from "./Starfield";

/**
 * AnimatedBackground - Creates a premium animated background with mouse-interactive starfield
 * Uses GPU-optimized transforms and requestAnimationFrame for smooth performance
 */
export const AnimatedBackground: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mousePosition, setMousePosition] = useState({ x: 0.5, y: 0.5 });

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        const y = (e.clientY - rect.top) / rect.height;
        
        // Smooth interpolation for subtle gradient movement
        setMousePosition((prev) => ({
          x: prev.x + (x - prev.x) * 0.05,
          y: prev.y + (y - prev.y) * 0.05,
        }));
      }
    };

    const container = containerRef.current;
    if (container) {
      container.addEventListener("mousemove", handleMouseMove);
      return () => {
        container.removeEventListener("mousemove", handleMouseMove);
      };
    }
  }, []);

  return (
    <div ref={containerRef} className="animated-background">
      {/* Base gradient layer */}
      <div className="animated-bg-layer animated-bg-base" />
      
      {/* Subtle mouse-reactive gradient layers */}
      <div
        className="animated-bg-layer animated-bg-gradient-1"
        style={{
          transform: `translate(${(mousePosition.x - 0.5) * 50}px, ${(mousePosition.y - 0.5) * 50}px)`,
        }}
      />
      <div
        className="animated-bg-layer animated-bg-gradient-2"
        style={{
          transform: `translate(${(mousePosition.x - 0.5) * -40}px, ${(mousePosition.y - 0.5) * -40}px)`,
        }}
      />
      
      {/* Interactive Starfield with parallax */}
      <Starfield
        numberOfStars={100}
        depthLayers={3}
        speed={0.5}
        starSizeRange={[1, 2.5]}
      />
    </div>
  );
};

