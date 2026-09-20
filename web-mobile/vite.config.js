import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Built assets are served by FastAPI from src/aoa/web/static/mobile
export default defineConfig({
  plugins: [react()],
  base: '/m/',
  build: {
    outDir: '../src/aoa/web/static/mobile',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      '/health': 'http://127.0.0.1:8080',
    },
  },
})
