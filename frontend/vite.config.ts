import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          "vendor-mantine": [
            "@mantine/core",
            "@mantine/hooks",
            "@mantine/notifications",
          ],
          "vendor-query": ["@tanstack/react-query"],
          "vendor-markdown": ["react-markdown"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    css: false,
  },
});
