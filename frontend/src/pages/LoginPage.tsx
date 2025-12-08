import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { AnimatedBackground } from "../components/AnimatedBackground";
import { FeatureCard } from "../components/FeatureCard";

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Check for OAuth callback errors (if user was redirected back from OAuth with an error)
    // NOTE: This does NOT call /oauth2callback - it only reads error params that might be in the URL
    // The actual OAuth callback is handled entirely by the backend at /oauth2callback
    const errorParam = searchParams.get("error");
    const errorDescription = searchParams.get("error_description");
    if (errorParam) {
      setError(errorDescription || "Authentication failed. Please try again.");
      // Clean up URL
      window.history.replaceState({}, "", "/login");
    }

    // Check if user is already logged in
    const checkAuth = async () => {
      try {
        const res = await fetch("/api/dashboard", { credentials: "include" });
        if (res.status === 200) {
          // Already logged in, redirect to dashboard
          navigate("/dashboard", { replace: true });
        }
      } catch (error) {
        // Not logged in, stay on login page
      }
    };
    checkAuth();
  }, [navigate, searchParams]);

  const handleLogin = () => {
    // Redirect to BACKEND login route (/login) which starts the OAuth flow
    // This is NOT the callback route - the callback (/oauth2callback) is only called by Google
    // Flow: Frontend → Backend /login → Google OAuth → Backend /oauth2callback → Frontend
    // Use window.location.replace to ensure full page navigation (bypasses React Router)
    window.location.replace("/login");
  };

  const features = [
    {
      icon: "📧",
      title: "Smart Email Organization",
      description:
        "Automatically categorize emails into meetings, tasks, and newsletters. Never miss important messages again.",
    },
    {
      icon: "🤖",
      title: "AI-Powered Insights",
      description:
        "Extract meetings, tasks, and actionable items from your emails using advanced AI classification.",
    },
    {
      icon: "✨",
      title: "Inbox Hygiene",
      description:
        "Identify and manage newsletters, junk mail, and unsubscribe links to keep your inbox clean and focused.",
    },
  ];

  return (
    <div className="login-page-premium">
      <AnimatedBackground />
      
      <motion.div
        className="login-container-premium"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8 }}
      >
        {/* Logo/Header */}
        <motion.div
          className="login-header-premium"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
        >
          <div className="login-logo-premium">
            <motion.div
              className="logo-pill-premium"
              initial={{ scale: 0, rotate: -180 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{
                type: "spring",
                stiffness: 200,
                damping: 15,
                delay: 0.3,
              }}
            >
              P
            </motion.div>
            <div className="brand-premium">
              <motion.span
                className="brand-name-premium"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.6, delay: 0.5 }}
              >
                Pare
              </motion.span>
              <motion.span
                className="brand-sub-premium"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.6, delay: 0.6 }}
              >
                Email Suite
              </motion.span>
            </div>
          </div>
          
          <motion.h1
            className="login-title-premium"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.4, ease: [0.16, 1, 0.3, 1] }}
          >
            Streamline your inbox with{" "}
            <span className="gradient-text">AI-powered workflows</span>
          </motion.h1>
          
          <motion.p
            className="login-tagline-premium"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.5, ease: [0.16, 1, 0.3, 1] }}
          >
            Transform your email into an organized, actionable workspace
          </motion.p>
        </motion.div>

        {/* Feature Cards */}
        <div className="login-features-premium">
          {features.map((feature, index) => (
            <FeatureCard
              key={index}
              icon={feature.icon}
              title={feature.title}
              description={feature.description}
              delay={0.7 + index * 0.1}
            />
          ))}
        </div>

        {/* Error Message */}
        {error && (
          <motion.div
            className="login-error-premium"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3 }}
          >
            <p>{error}</p>
          </motion.div>
        )}

        {/* Sign In Button */}
        <motion.div
          className="login-actions-premium"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 1 }}
        >
          <motion.button
            className="login-button-premium"
            onClick={handleLogin}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            transition={{ type: "spring", stiffness: 400, damping: 17 }}
          >
            <span>Sign in with Google</span>
            <motion.div
              className="button-glow"
              initial={{ opacity: 0 }}
              whileHover={{ opacity: 1 }}
              transition={{ duration: 0.3 }}
            />
          </motion.button>
          
          <motion.p
            className="login-privacy-premium"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 1.1 }}
          >
            By signing in, you agree to our terms of service and privacy policy.
          </motion.p>
        </motion.div>
      </motion.div>
    </div>
  );
};
