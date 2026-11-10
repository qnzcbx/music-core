import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import Icons from 'unplugin-icons/vite'

export default defineConfig(({ mode }) => ({
  plugins: [vue(), tailwindcss(), Icons({ compiler: 'vue3', autoInstall: false })],
  server: { port: 5174, strictPort: true, proxy: { '/api': loadEnv(mode, '.', 'MUSIC_CORE_').MUSIC_CORE_API_TARGET || 'http://127.0.0.1:8001' } },
}))
