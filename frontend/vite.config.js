import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development, /api and /media are proxied to Django on port 8000 (no CORS setup needed).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000', '/media': 'http://127.0.0.1:8000' },
  },
})
