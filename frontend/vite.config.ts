import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  if (mode === "production" && env.VITE_USE_MOCK_BACKTEST === "true") {
    throw new Error(
      "VITE_USE_MOCK_BACKTEST=true is forbidden in production builds. Use the real backtest API.",
    );
  }

    return {
    plugins: [react()],

    server: {
    host: "0.0.0.0",

    allowedHosts: [
      "ca-frontend-fein.livelystone-0567c409.koreacentral.azurecontainerapps.io",
      "ca-frontend-fein-vnet.lemonmushroom-480bc7ea.koreacentral.azurecontainerapps.io",
    ],

    watch: {
      usePolling: true,
    },

    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
      },
  };
});
