import { defineConfig } from "@playwright/test";

/** E2E tests expect the backend on :8000 (demo mode) and the frontend on :3000 — e.g. `docker compose up`. */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", trace: "retain-on-failure" },
  webServer: process.env.E2E_NO_SERVER ? undefined : { command: "npm run start", port: 3000, reuseExistingServer: true },
});
