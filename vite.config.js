import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  root: "src",
  base: "./",
  build: {
    outDir: path.resolve(__dirname, "dist"),
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(__dirname, "src/index.html"),
    },
  },
  server: {
    port: 3000,
    strictPort: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    include: ["tests/**/*.test.{js,jsx}"],
    setupFiles: ["tests/setup.js"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      reportsDirectory: "./coverage",
      // Only measure coverage on files that have tests written for them
      include: [
        "api-client.js",
        "components/**/*.{js,jsx}",
        "pages/**/*.{js,jsx}",
      ],
      // Exclude files that are Electron/app shell (no unit tests expected)
      exclude: [
        "main.jsx",
        "GhostBackup.jsx",
        "splash.css",
        "styles.css",
        "index.html",
        "tests/**",
      ],
    },
  },
});
