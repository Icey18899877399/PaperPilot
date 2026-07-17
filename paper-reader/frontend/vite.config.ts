import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  base: mode === "github" ? "/PaperPilot/" : "/",
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "react-vendor": ["react", "react-dom"],
          "pdf-vendor": ["react-pdf", "pdfjs-dist"],
          "markmap-vendor": ["markmap-lib", "markmap-view"]
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/media": "http://localhost:8000"
    }
  }
}));

