import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

const BACKEND = process.env.HERMES_DASHBOARD_URL ?? "http://127.0.0.1:9119";

/**
 * In production the Python `hermes dashboard` server injects a one-shot
 * session token into `index.html` (see `hermes_cli/web_server.py`). The
 * Vite dev server serves its own `index.html`, so unless we forward that
 * token, every protected `/api/*` call 401s.
 *
 * This plugin fetches the running dashboard's `index.html` on each dev page
 * load, scrapes the `window.__HERMES_SESSION_TOKEN__` assignment, and
 * re-injects it into the dev HTML. No-op in production builds.
 */
function hermesDevToken(): Plugin {
  const TOKEN_RE = /window\.__HERMES_SESSION_TOKEN__\s*=\s*"([^"]+)"/;
  const EMBEDDED_RE =
    /window\.__HERMES_DASHBOARD_EMBEDDED_CHAT__\s*=\s*(true|false)/;
  const LEGACY_TUI_RE =
    /window\.__HERMES_DASHBOARD_TUI__\s*=\s*(true|false)/;

  return {
    name: "hermes:dev-session-token",
    apply: "serve",
    async transformIndexHtml() {
      try {
        const res = await fetch(BACKEND, { headers: { accept: "text/html" } });
        const html = await res.text();
        const match = html.match(TOKEN_RE);
        if (!match) {
          console.warn(
            `[hermes] Could not find session token in ${BACKEND} — ` +
              `is \`hermes dashboard\` running? /api calls will 401.`,
          );
          return;
        }
        const embeddedMatch = html.match(EMBEDDED_RE);
        const legacyMatch = html.match(LEGACY_TUI_RE);
        const embeddedJs = embeddedMatch
          ? embeddedMatch[1]
          : legacyMatch
            ? legacyMatch[1]
            : "false";
        return [
          {
            tag: "script",
            injectTo: "head",
            children:
              `window.__HERMES_SESSION_TOKEN__="${match[1]}";` +
              `window.__HERMES_DASHBOARD_EMBEDDED_CHAT__=${embeddedJs};`,
          },
        ];
      } catch (err) {
        console.warn(
          `[hermes] Dashboard at ${BACKEND} unreachable — ` +
            `start it with \`hermes dashboard\` or set HERMES_DASHBOARD_URL. ` +
            `(${(err as Error).message})`,
        );
      }
    },
  };
}

/**
 * Dev-only middleware that gives the Quick Chat page server-side web-search
 * and URL-fetch capabilities without CORS issues.
 */
function hermesToolProxy(): Plugin {
  return {
    name: "hermes:tool-proxy",
    apply: "serve",
    configureServer(server) {
      // Web search via DuckDuckGo HTML
      server.middlewares.use("/proxy/search", async (req, res) => {
        const url = new URL(req.url ?? "/", "http://localhost");
        const q = url.searchParams.get("q");
        if (!q) { res.writeHead(400); res.end("Missing ?q="); return; }
        try {
          const r = await fetch(`https://html.duckduckgo.com/html/?q=${encodeURIComponent(q)}`, {
            headers: { "User-Agent": "Mozilla/5.0 (compatible; HermesAgent/1.0)" },
          });
          const html = await r.text();
          // Extract result snippets from DDG HTML
          const results: { title: string; url: string; snippet: string }[] = [];
          const re = /<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)<\/a>[\s\S]*?<a[^>]+class="result__snippet"[^>]*>(.*?)<\/a>/gi;
          let m;
          while ((m = re.exec(html)) !== null && results.length < 8) {
            results.push({
              url: m[1].replace(/.*uddg=([^&]+).*/, (_, u) => decodeURIComponent(u)),
              title: m[2].replace(/<[^>]+>/g, "").trim(),
              snippet: m[3].replace(/<[^>]+>/g, "").trim(),
            });
          }
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ query: q, results }));
        } catch (e) {
          res.writeHead(502);
          res.end(JSON.stringify({ error: (e as Error).message }));
        }
      });

      // URL fetch — returns extracted text
      server.middlewares.use("/proxy/fetch", async (req, res) => {
        const url = new URL(req.url ?? "/", "http://localhost");
        const target = url.searchParams.get("url");
        if (!target) { res.writeHead(400); res.end("Missing ?url="); return; }
        try {
          const r = await fetch(target, {
            headers: { "User-Agent": "Mozilla/5.0 (compatible; HermesAgent/1.0)" },
            signal: AbortSignal.timeout(10000),
          });
          const ct = r.headers.get("content-type") ?? "";
          let text: string;
          if (ct.includes("json")) {
            text = JSON.stringify(await r.json(), null, 2);
          } else {
            const raw = await r.text();
            // Strip HTML tags for basic text extraction
            text = raw
              .replace(/<script[\s\S]*?<\/script>/gi, "")
              .replace(/<style[\s\S]*?<\/style>/gi, "")
              .replace(/<[^>]+>/g, " ")
              .replace(/\s{2,}/g, " ")
              .trim()
              .slice(0, 12000);
          }
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ url: target, text }));
        } catch (e) {
          res.writeHead(502);
          res.end(JSON.stringify({ error: (e as Error).message }));
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), hermesDevToken(), hermesToolProxy()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    dedupe: [
      "react",
      "react-dom",
      "@react-three/fiber",
      "@observablehq/plot",
      "three",
      "leva",
      "gsap",
    ],
  },
  build: {
    outDir: "../hermes_cli/web_dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": {
        target: BACKEND,
        ws: true,
      },
      "/dashboard-plugins": BACKEND,
    },
  },
});

