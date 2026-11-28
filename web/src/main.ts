import { createApp } from 'vue';
import { desktopPlatform, isDesktop } from './platform/desktop';

const params = new URLSearchParams(location.search);
if (params.has('desktop-lyrics') && isDesktop) {
  const platform = await desktopPlatform().catch(() => null);
  const lyricsWindow = params.has('settings') ? 'desktop-lyrics-settings' : 'desktop-lyrics';
  if (platform?.window === lyricsWindow && platform.desktopLyrics) {
    const { default: DesktopLyrics } = await import('./components/DesktopLyrics.vue');
    createApp(DesktopLyrics).mount('#app');
  } else if (platform?.window === 'main') {
    await import('./main-player');
  }
} else {
  await import('./main-player');
}
