/** @type {import('next').NextConfig} */
// Exporta o site como arquivos estáticos (web/out), servidos pela API FastAPI.
const nextConfig = { output: "export", trailingSlash: true, images: { unoptimized: true } };
export default nextConfig;
