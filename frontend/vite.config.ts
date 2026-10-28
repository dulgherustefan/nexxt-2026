import { defineConfig, loadEnv, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * Moduri:
 * - `vite`            → proxy spre zona client (:8000)
 * - `vite --mode aml` → proxy spre zona AML (:8001)
 * - `vite --mode mock` → fără backend: fixtures + simularea demo-ului
 * `VITE_API_TARGET` și `VITE_MOCK=1` din mediu au prioritate.
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target =
    env.VITE_API_TARGET || process.env.VITE_API_TARGET || (mode === "aml" ? "http://127.0.0.1:8001" : "http://127.0.0.1:8000");
  const mock = env.VITE_MOCK || process.env.VITE_MOCK || (mode === "mock" ? "1" : "");

  const proxy: Record<string, ProxyOptions> = {
    "/api": { target, changeOrigin: true },
    "/diode": { target, changeOrigin: true },
  };

  return {
    // Căi absolute de la rădăcină: merg la „/" și pe rutele adânci (/cazuri/CT-…), cu fallback SPA pe server.
    base: "/",
    plugins: [react(), tailwindcss()],
    define: {
      "import.meta.env.VITE_MOCK": JSON.stringify(mock),
    },
    server: { port: 5173, host: true, proxy },
    preview: { port: 4173, host: true, proxy },
    build: {
      outDir: "dist",
      assetsDir: "assets",
      sourcemap: false,
      chunkSizeWarningLimit: 1600,
    },
  };
});
