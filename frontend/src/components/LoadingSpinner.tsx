import React from "react";
import { Card } from "./Card";

interface LoadingSpinnerProps {
  message?: string;
  fullHeight?: boolean;
}

/**
 * LoadingSpinner - Premium loading component with animated spinner
 */
export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  message = "Loading...",
  fullHeight = false,
}) => {
  return (
    <Card className={fullHeight ? "loading-spinner-full" : ""}>
      <div className="loading-spinner-container">
        <div className="loading-spinner">
          <div className="spinner-ring"></div>
          <div className="spinner-ring"></div>
          <div className="spinner-ring"></div>
        </div>
        <p className="loading-spinner-text">{message}</p>
      </div>
    </Card>
  );
};

