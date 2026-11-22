import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import path from "node:path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const hmrPort = env.VITE_HMR_CLIENT_PORT ? Number(env.VITE_HMR_CLIENT_PORT) : undefined;
  return {
    plugins: [
      react(),
      VitePWA({
        // One service worker, for web push only (P-11): src/sw.ts. P-92 / E-29: no precache list is injected and the
        // worker has no fetch handler, so every opening takes index.html from the network; the new version of an open
        // page is src/lib/appVersion.ts. The plugin still builds the worker, registers it (registerSW.js) and writes
        // the manifest.
        strategies: "injectManifest",
        srcDir: "src",
        filename: "sw.ts",
        injectManifest: { injectionPoint: undefined },
        registerType: "autoUpdate",
        devOptions: {
          // No worker in Vite dev: push and the worker are checked on the production build (P-92: the new-version
          // watch is off there too, the page has no /assets/ files).
          enabled: false,
        },
        manifest: {
          // Same name as app.name in src/i18n/it.json and the <title> of index.html (D-76).
          name: "DOMHOUSE",
          short_name: "DOMHOUSE",
          description: "Gestione di riscaldamento, clima e consumi degli appartamenti",
          lang: "it",
          start_url: "/",
          display: "standalone",
          background_color: "#F5FAF8",
          theme_color: "#0D6B61",
          icons: [
            { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
            { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
            { src: "/icons/maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
            { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
          ],
        },
      }),
    ],
    resolve: { alias: { "@": path.resolve(__dirname, "src") } },
    build: {
      rollupOptions: {
        output: {
          // React and the router change only on upgrades: their own block stays cached on the phone across releases (P-20).
          manualChunks: { vendor: ["react", "react-dom", "react-router-dom"] },
        },
      },
    },
    server: {
      host: "0.0.0.0",
      // 5173: the only localhost referrer of the web API key (D-52, P-45); strictPort, so it never moves to another one.
      port: 5173,
      strictPort: true,
      allowedHosts: true,
      hmr: hmrPort ? { clientPort: hmrPort, protocol: "wss" } : undefined,
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
    },
  };
});
