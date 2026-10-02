import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    // O FastAPI serve esta pasta: depois do build, `python -m qai` basta, sem Node.
    outDir: '../qai/web/dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    // Em desenvolvimento o Vite serve o React e repassa a API para o FastAPI.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
});
