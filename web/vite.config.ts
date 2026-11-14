import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import Icons from 'unplugin-icons/vite';
import { existsSync } from 'node:fs';
import { extname, resolve, sep } from 'node:path';

export default defineConfig(({ mode }) => ({
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  plugins: [
    vue(),
    tailwindcss(),
    Icons({ compiler: 'vue3', autoInstall: false }),
    {
      name: 'preview-static-not-found',
      configurePreviewServer(server) {
        const root = resolve(server.config.root, server.config.build.outDir);
        server.middlewares.use((request, response, next) => {
          let path: string;
          try {
            path = decodeURIComponent(new URL(request.url || '/', 'http://preview').pathname);
          } catch {
            return next();
          }
          const base = server.config.base;
          if (base !== '/' && path.startsWith(base)) path = '/' + path.slice(base.length);
          // API 留给现有代理；只有页面路径进入 SPA 回退，缺失的静态文件返回真实 404。
          if (path === '/api' || path.startsWith('/api/')) return next();
          if (!path.startsWith('/assets/') && !extname(path)) return next();
          const file = resolve(root, '.' + path);
          if (file.startsWith(root + sep) && existsSync(file)) return next();
          response.statusCode = 404;
          response.setHeader('Content-Type', 'text/plain; charset=utf-8');
          response.end(request.method === 'HEAD' ? undefined : 'Not found');
        });
      },
    },
  ],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': loadEnv(mode, '.', 'MUSIC_CORE_').MUSIC_CORE_API_TARGET || 'http://127.0.0.1:8001',
    },
  },
}));
