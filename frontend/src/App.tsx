import React, { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { MeetingsPage } from "./pages/MeetingsPage";
import { TasksPage } from "./pages/TasksPage";
import { JunkPage } from "./pages/JunkPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { LoadingSpinner } from "./components/LoadingSpinner";

// Protected route wrapper - redirects to login if not authenticated
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const res = await fetch("/api/dashboard", { credentials: "include" });
        setIsAuthenticated(res.status === 200);
        if (res.status !== 200) {
          navigate("/login", { replace: true });
        }
      } catch (error) {
        setIsAuthenticated(false);
        navigate("/login", { replace: true });
      }
    };
    checkAuth();
  }, [navigate]);

  if (isAuthenticated === null) {
    // Still checking auth
    return <LoadingSpinner message="Checking authentication..." />;
  }

  if (!isAuthenticated) {
    return null; // Will redirect via navigate
  }

  return <>{children}</>;
};

// Root redirect - checks auth and redirects appropriately
const RootRedirect: React.FC = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const res = await fetch("/api/dashboard", { credentials: "include" });
        setIsAuthenticated(res.status === 200);
      } catch (error) {
        setIsAuthenticated(false);
      }
    };
    checkAuth();
  }, []);

  if (isAuthenticated === null) {
    return <LoadingSpinner message="Loading..." />;
  }

  return <Navigate to={isAuthenticated ? "/dashboard" : "/login"} replace />;
};

const App: React.FC = () => {
  // NOTE: /oauth2callback is explicitly excluded from React Router routes
  // This route must be handled exclusively by the backend Flask server
  // If this component renders for /oauth2callback, it means the server
  // incorrectly served index.html (should be fixed at server level)
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RootRedirect />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <Layout>
              <DashboardPage />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/meetings"
        element={
          <ProtectedRoute>
            <Layout>
              <MeetingsPage />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/tasks"
        element={
          <ProtectedRoute>
            <Layout>
              <TasksPage />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/junk"
        element={
          <ProtectedRoute>
            <Layout>
              <JunkPage />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/analytics"
        element={
          <ProtectedRoute>
            <Layout>
              <AnalyticsPage />
            </Layout>
          </ProtectedRoute>
        }
      />
      {/* 
        CRITICAL: /oauth2callback is NOT listed here - it must never be handled by React Router.
        This route is exclusively handled by the backend Flask server at /oauth2callback.
        The Vite proxy forwards it to the backend in development.
        In production, the server must be configured to NOT serve index.html for /oauth2callback.
      */}
    </Routes>
  );
};

export default App;


