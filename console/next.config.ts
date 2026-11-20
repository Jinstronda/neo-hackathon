import type { NextConfig } from 'next';

// the footer shows the deployed commit; Vercel sets VERCEL_GIT_COMMIT_SHA on Git builds
const config: NextConfig = { env: { NEXT_PUBLIC_COMMIT_SHA: process.env.VERCEL_GIT_COMMIT_SHA ?? '' } };
export default config;
