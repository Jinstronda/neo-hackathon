// Server-only. For local dev the gateway key lives in the repo-root .env
// (../.env), not in web/. Next loads web/.env* on its own; this backfills the
// key from the repo root when it is missing. Never imported by client code.
import { promises as fs } from "fs";
import path from "path";

let tried = false;

export async function ensureGatewayKey(): Promise<string | undefined> {
  if (process.env.HOMODEUS_API_KEY) return process.env.HOMODEUS_API_KEY;
  if (tried) return undefined;
  tried = true;
  try {
    const raw = await fs.readFile(path.join(process.cwd(), "..", ".env"), "utf8");
    for (const line of raw.split("\n")) {
      const t = line.trim();
      if (!t || t.startsWith("#") || !t.includes("=")) continue;
      const [k, ...rest] = t.split("=");
      if (!process.env[k.trim()]) process.env[k.trim()] = rest.join("=").trim();
    }
  } catch {
    // no repo-root .env; rely on the platform env var (Vercel).
  }
  return process.env.HOMODEUS_API_KEY;
}
