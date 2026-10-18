import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The build goes inside the Python package, so the PC only needs `git pull`.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../agent/src/raceengineer/api/static",
    emptyOutDir: true,
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
