import { loadRun } from "@/lib/run";

export const dynamic = "force-dynamic";

export async function GET() {
  const run = await loadRun();
  return Response.json(run);
}
