import { defineConfig } from "vite";

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    include: ["electron/tests/**/*.test.{js,mjs}"],
  },
});
