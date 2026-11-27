import { createApp } from 'vue';
import { desktopPlatform, isDesktop } from './platform/desktop';

const lyricsRequested = new URLSearchParams(location.search).has('desktop-lyrics');
if (lyricsRequested && isDesktop) {
  const platform = await desktopPlatform().catch(() => null);
  if (platform?.window === 'desktop-lyrics' && platform.desktopLyrics) {
    const { default: DesktopLyrics } = await import('./components/DesktopLyrics.vue');
    createApp(DesktopLyrics).mount('#app');
  } else if (platform?.window === 'main') {
    await import('./main-player');
  }
} else {
  await import('./main-player');
}
