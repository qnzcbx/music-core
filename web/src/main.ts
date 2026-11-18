import { createApp } from 'vue'

if (new URLSearchParams(location.search).has('desktop-lyrics') && '__TAURI_INTERNALS__' in window) {
  const { default: DesktopLyrics } = await import('./components/DesktopLyrics.vue')
  createApp(DesktopLyrics).mount('#app')
} else {
  await import('./main-player')
}
