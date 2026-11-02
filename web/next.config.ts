import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output lets the Docker image ship only what the server needs.
  output: "standalone",
  reactStrictMode: true,
  // Tailwind v4 runs as a Turbopack loader (no PostCSS config needed).
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
