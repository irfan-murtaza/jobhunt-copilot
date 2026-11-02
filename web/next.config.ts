import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output lets the Docker image ship only what the server needs.
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
