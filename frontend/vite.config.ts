import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

// Vite config: dev server on 5173 by default.
// For production, you can set build.outDir to "../static/app"
// and serve the built assets from Flask if desired.

export default defineConfig({
  plugins: [
    react(),
    // Plugin to prevent /oauth2callback from being handled by SPA fallback
    {
      name: "prevent-oauth-callback-spa-fallback",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          // If request is for /oauth2callback, don't serve index.html
          // Let the proxy handle it instead
          if (req.url?.startsWith("/oauth2callback")) {
            // Return 404 so proxy can handle it, or pass through
            // The proxy will intercept it before this middleware runs
            return next();
          }
          next();
        });
      },
    },
  ],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://localhost:5001",
        changeOrigin: true,
      },
      "/login": {
        target: "http://localhost:5001",
        changeOrigin: true,
      },
      "/logout": {
        target: "http://localhost:5001",
        changeOrigin: true,
      },
      "/open_email": {
        target: "http://localhost:5001",
        changeOrigin: true,
      },
      "/sync": {
        target: "http://localhost:5001",
        changeOrigin: true,
      },
      // CRITICAL: Proxy /oauth2callback to backend BEFORE SPA fallback
      // This ensures OAuth callback with query params reaches Flask
      "/oauth2callback": {
        target: "http://localhost:5001",
        changeOrigin: true,
        // Preserve query parameters
        rewrite: (path) => path,
      },
    },
  },
  // Build configuration
  build: {
    rollupOptions: {
      // Ensure /oauth2callback is not included in build
      external: [],
    },
  },
});


