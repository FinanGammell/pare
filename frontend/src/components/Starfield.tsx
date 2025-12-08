import React, { useEffect, useRef, useState } from "react";

export interface StarfieldProps {
  numberOfStars?: number;
  depthLayers?: number;
  speed?: number;
  starSizeRange?: [number, number];
}

/**
 * Starfield - Premium mouse-interactive starfield with parallax depth effect
 * Uses direct DOM manipulation and requestAnimationFrame for 60fps performance
 */
export const Starfield: React.FC<StarfieldProps> = ({
  numberOfStars = 100, // Reduced from 150 for better performance
  depthLayers = 3,
  speed = 0.5,
  starSizeRange = [1, 3],
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const starsRef = useRef<HTMLDivElement[]>([]);
  const animationFrameRef = useRef<number>();
  
  const targetMousePosition = useRef({ x: 0, y: 0 });
  const currentMousePosition = useRef({ x: 0, y: 0 });
  const containerDimensions = useRef({ width: 0, height: 0 });
  const lastUpdateTime = useRef(0);
  
  // Generate stars with random properties
  const stars = useRef(
    Array.from({ length: numberOfStars }).map((_, i) => {
      const depth = Math.floor((i / numberOfStars) * depthLayers) + 1;
      const depthFactor = depth / depthLayers; // 0.33, 0.66, 1.0
      
      return {
        id: i,
        baseX: Math.random() * 100, // Percentage position
        baseY: Math.random() * 100, // Percentage position
        size: Math.random() * (starSizeRange[1] - starSizeRange[0]) + starSizeRange[0],
        depth,
        depthFactor,
        opacity: 0.3 + depthFactor * 0.5, // Deeper stars are brighter
        driftX: (Math.random() - 0.5) * 0.5, // Slow floating drift
        driftY: (Math.random() - 0.5) * 0.5,
        driftTime: Math.random() * Math.PI * 2, // Random phase for drift
      };
    })
  );

  // Cache container dimensions and update on resize
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const width = containerRef.current.offsetWidth;
        const height = containerRef.current.offsetHeight;
        
        // Only update if dimensions actually changed
        if (containerDimensions.current.width !== width || containerDimensions.current.height !== height) {
          containerDimensions.current = { width, height };
          
          // Recalculate all base positions when container size changes
          if (width > 0 && height > 0) {
            stars.current.forEach((star, index) => {
              const basePx = starsBasePx.current[index];
              basePx.baseXPx = (star.baseX / 100) * width;
              basePx.baseYPx = (star.baseY / 100) * height;
            });
          }
        }
      }
    };

    // Use a small delay to ensure container is rendered
    const timeoutId = setTimeout(updateDimensions, 0);
    updateDimensions();
    
    window.addEventListener("resize", updateDimensions);
    return () => {
      clearTimeout(timeoutId);
      window.removeEventListener("resize", updateDimensions);
    };
  }, []);

  // Mouse tracking with throttling
  useEffect(() => {
    let rafId: number | null = null;
    
    const handleMouseMove = (e: MouseEvent) => {
      // Throttle using requestAnimationFrame
      if (rafId === null) {
        rafId = requestAnimationFrame(() => {
          // Normalize mouse position to -1 to 1 range
          const x = (e.clientX / window.innerWidth) * 2 - 1;
          const y = (e.clientY / window.innerHeight) * 2 - 1;
          
          targetMousePosition.current = { x, y };
          rafId = null;
        });
      }
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
    };
  }, []);

  // Pre-calculate base positions in pixels (will be set on first frame)
  const starsBasePx = useRef<Array<{ baseXPx: number; baseYPx: number }>>(
    stars.current.map(() => ({ baseXPx: -1, baseYPx: -1 })) // Use -1 as uninitialized flag
  );
  const lastContainerSize = useRef({ width: 0, height: 0 });

  // Animation loop with lerping and optimizations
  useEffect(() => {
    let mounted = true;
    
    const animate = (currentTime: number) => {
      if (!mounted) return;
      
      // Throttle to ~60fps and skip if too soon
      const timeDelta = currentTime - lastUpdateTime.current;
      if (timeDelta < 16) { // ~60fps
        animationFrameRef.current = requestAnimationFrame(animate);
        return;
      }
      lastUpdateTime.current = currentTime;
      
      // Smooth lerp toward target mouse position (easing)
      const lerpFactor = 0.15; // Slightly faster for responsiveness
      const dx = targetMousePosition.current.x - currentMousePosition.current.x;
      const dy = targetMousePosition.current.y - currentMousePosition.current.y;
      
      // Only update if change is significant (reduces unnecessary updates)
      if (Math.abs(dx) > 0.001 || Math.abs(dy) > 0.001) {
        currentMousePosition.current.x += dx * lerpFactor;
        currentMousePosition.current.y += dy * lerpFactor;
      }
      
      // Get cached container dimensions
      const { width: containerWidth, height: containerHeight } = containerDimensions.current;
      if (containerWidth === 0 || containerHeight === 0) {
        animationFrameRef.current = requestAnimationFrame(animate);
        return;
      }
      
      // Recalculate base positions if container size changed
      const containerSizeChanged = 
        lastContainerSize.current.width !== containerWidth || 
        lastContainerSize.current.height !== containerHeight;
      
      if (containerSizeChanged) {
        lastContainerSize.current = { width: containerWidth, height: containerHeight };
        stars.current.forEach((star, index) => {
          const basePx = starsBasePx.current[index];
          basePx.baseXPx = (star.baseX / 100) * containerWidth;
          basePx.baseYPx = (star.baseY / 100) * containerHeight;
        });
      }
      
      // Pre-calculate common values
      const time = currentTime * 0.001; // Time in seconds for drift
      const parallaxBaseX = -currentMousePosition.current.x * speed * 50;
      const parallaxBaseY = -currentMousePosition.current.y * speed * 50;
      const driftTimeX = time * 0.3;
      const driftTimeY = time * 0.4;
      const containerWidth100 = containerWidth / 100;
      const containerHeight100 = containerHeight / 100;

      // Batch DOM updates
      stars.current.forEach((star, index) => {
        const starElement = starsRef.current[index];
        if (!starElement) return;

        // Get cached base position (should be initialized by now)
        const basePx = starsBasePx.current[index];
        
        // Initialize if not set (fallback)
        if (basePx.baseXPx < 0 || basePx.baseYPx < 0) {
          basePx.baseXPx = (star.baseX / 100) * containerWidth;
          basePx.baseYPx = (star.baseY / 100) * containerHeight;
        }

        // Calculate parallax offset (deeper stars move more)
        const parallaxX = parallaxBaseX * star.depthFactor;
        const parallaxY = parallaxBaseY * star.depthFactor;

        // Add slow floating drift (pre-calculate sin/cos)
        const driftOffsetX = Math.sin(driftTimeX + star.driftTime) * star.driftX * containerWidth100;
        const driftOffsetY = Math.cos(driftTimeY + star.driftTime) * star.driftY * containerHeight100;

        // Calculate final position
        const finalX = basePx.baseXPx + parallaxX + driftOffsetX;
        const finalY = basePx.baseYPx + parallaxY + driftOffsetY;

        // Apply transform (use template literal for better performance)
        starElement.style.transform = `translate3d(${finalX.toFixed(2)}px,${finalY.toFixed(2)}px,0)`;
      });

      animationFrameRef.current = requestAnimationFrame(animate);
    };

    animationFrameRef.current = requestAnimationFrame(animate);

    return () => {
      mounted = false;
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [speed]);

  return (
    <div ref={containerRef} className="starfield-container">
      {stars.current.map((star, index) => (
        <div
          key={star.id}
          ref={(el) => {
            if (el) starsRef.current[index] = el;
          }}
          className="starfield-star"
          style={{
            width: `${star.size}px`,
            height: `${star.size}px`,
            opacity: star.opacity,
            willChange: "transform",
          }}
        />
      ))}
    </div>
  );
};

