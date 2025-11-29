import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Check for OAuth callback errors
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
    window.location.href = "/login";
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-header">
          <div className="login-logo">
            <div className="logo-pill-large">P</div>
            <div className="brand">
              <span className="brand-name">Pare</span>
              <span className="brand-sub">Email Suite</span>
            </div>
          </div>
          <p className="login-tagline">
            Streamline your inbox with AI-powered workflows
          </p>
        </div>

        <div className="login-features">
          <div className="feature-box">
            <div className="feature-icon">📧</div>
            <h3 className="feature-title">Smart Email Organization</h3>
            <p className="feature-description">
              Automatically categorize emails into meetings, tasks, and newsletters.
              Never miss important messages again.
            </p>
          </div>

          <div className="feature-box">
            <div className="feature-icon">🤖</div>
            <h3 className="feature-title">AI-Powered Insights</h3>
            <p className="feature-description">
              Extract meetings, tasks, and actionable items from your emails
              using advanced AI classification.
            </p>
          </div>

          <div className="feature-box">
            <div className="feature-icon">✨</div>
            <h3 className="feature-title">Inbox Hygiene</h3>
            <p className="feature-description">
              Identify and manage newsletters, junk mail, and unsubscribe links
              to keep your inbox clean and focused.
            </p>
          </div>
        </div>

        {error && (
          <div className="card error" style={{ textAlign: "center" }}>
            <p style={{ margin: 0, color: "#fca5a5" }}>{error}</p>
          </div>
        )}

        <div className="login-actions">
          <button className="primary-button large-button" onClick={handleLogin}>
            Sign in with Google
          </button>
          <p className="login-privacy">
            By signing in, you agree to our terms of service and privacy policy.
          </p>
        </div>
      </div>
    </div>
  );
};

