import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The run artifact lives outside web/ (../runs/demo-run). Reading it happens
  // in a route handler at request time, so no build-time file tracing is needed.
  outputFileTracingRoot: process.cwd(),
};

export default nextConfig;
