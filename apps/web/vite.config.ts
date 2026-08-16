import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Backend API target — override with GREENFLEX_API_PORT if backend runs elsewhere
const backendPort = process.env.GREENFLEX_API_PORT || '8000'
const backendTarget = `http://127.0.0.1:${backendPort}`

// Frontend dev server port — override with VITE_PORT if 5173 is taken
const frontendPort = parseInt(process.env.VITE_PORT || '5173', 10)

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: frontendPort,
    strictPort: false, // auto-increment to 5174, 5175… if port is taken
    proxy: {
      '/api': backendTarget,
      '/health': backendTarget,
      '/metrics': backendTarget,
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      thresholds: { lines: 80 },
    },
  },
})
