/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, the browser talks to the Vite server, which plays nginx's part: /api/<svc>/ is proxied to
// the service and the prefix is stripped. Defaults point every service at the mock server
// (`npm run dev:mock`); override with the same env vars the nginx container uses.
const mock = process.env.MOCK_URL ?? "http://127.0.0.1:8090";
const target = (name: string) => process.env[name] ?? mock;
const proxy = (prefix: string, envName: string) => ({
  [`/api/${prefix}`]: {
    target: target(envName),
    changeOrigin: true,
    ws: true,
    rewrite: (p: string) => p.replace(new RegExp(`^/api/${prefix}`), ""),
  },
});

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      ...proxy("core", "CORE_BANK_URL"),
      ...proxy("scoring", "SCORING_URL"),
      ...proxy("case", "CASE_SVC_URL"),
      ...proxy("conversation", "CONVERSATION_SVC_URL"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    testTimeout: 15000,
  },
});
