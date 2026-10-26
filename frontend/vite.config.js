import { studioRoutes } from "./routing.mjs";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.CASEPROOF_API_TARGET || "http://127.0.0.1:8080";
  return {
    plugins: [react(), studioRoutes()],
    base: "/app/",
    server: {
      proxy: {
        "/v1": { target, changeOrigin: false },
        "/health": { target, changeOrigin: false },
        "/customer": { target, changeOrigin: false },
      },
    },
    test: {
      testTimeout: 15000,
      hookTimeout: 15000,
      maxWorkers: 2,
      environment: "jsdom",
      globals: true,
      include: ["tests/**/*.test.{js,jsx}"],
    },
  };
});
