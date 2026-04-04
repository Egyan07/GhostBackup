import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

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
    include: ["tests/**/*.test.{js,jsx,ts,tsx}"],
    setupFiles: ["tests/setup.js"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      reportsDirectory: "./coverage",
      include: [
        "api-client.{js,ts}",
        "components/**/*.{js,jsx,ts,tsx}",
        "pages/**/*.{js,jsx,ts,tsx}",
      ],
      exclude: [
        "main.{jsx,tsx}",
        "GhostBackup.{jsx,tsx}",
        "splash.css",
        "styles.css",
        "index.html",
        "tests/**",
        "types.ts",
        "global.d.ts",
      ],
    },
  },
});
