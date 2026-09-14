import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

const backend = process.env.VITE_BACKEND_URL ?? 'http://127.0.0.1:8000' // not localhost: Node may try ::1 first and stall

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    // IPv4 loopback only: Node would otherwise bind ::1 alone and Chrome stalls ~2s when it tries 127.0.0.1
    // first. Not '::' or true: that exposes the dev server (with dev-login) on the LAN.
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': backend,
      '/auth': backend,
      '/admin': backend,
      '/static': backend,
      '/ws': { target: backend.replace('http', 'ws'), ws: true },
    },
  },
  test: {
    environment: 'node',
    passWithNoTests: true,
  },
})
