import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/participant/',
  plugins: [react()],
  server: { port: 5174 },
})
