import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

// Vite config: dev server on 5173 by default.
// For production, you can set build.outDir to "../static/app"
// and serve the built assets from Flask if desired.

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
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
    },
  },
});


