import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, /api is proxied to the backend so the browser sees one origin
// (session cookie works, no CORS needed). In Docker, nginx does the same.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": process.env.VITE_BACKEND_URL ?? "http://localhost:8000" },
  },
});
