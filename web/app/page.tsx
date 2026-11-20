import { loadRun } from "@/lib/run";
import Shell from "@/components/Shell";

export const dynamic = "force-dynamic";

export default async function Page() {
  const data = await loadRun();
  return <Shell data={data} />;
}
