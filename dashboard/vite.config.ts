import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In dev, /api goes to the analyzer on the host. In Docker, nginx does the same (nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") } },
  },
  test: { environment: "jsdom" },
});
