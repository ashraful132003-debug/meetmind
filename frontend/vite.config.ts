import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // The SPA talks to /api on its own origin and Vite proxies it to FastAPI.
    // This keeps the refresh cookie same-site in development, exactly as it will
    // be in production behind one domain - so cookie behaviour is not something
    // that only starts working after deploy.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
