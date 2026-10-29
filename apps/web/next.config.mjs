/** @type {import('next').NextConfig} */
const nextConfig = {
  // standalone output for a slim Docker image
  output: "standalone",
  env: {
    // FastAPI backend URL (must be reachable from the browser; inlined at build time)
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000",
  },
};

export default nextConfig;
