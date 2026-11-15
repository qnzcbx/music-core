import { readonly, ref } from 'vue';

export type HomeBackground = 'ink' | 'voice';
export const HOME_BACKGROUND_KEY = 'media-lab.home-background.v1';

function readBackground(): HomeBackground {
  try {
    return localStorage.getItem(HOME_BACKGROUND_KEY) === 'voice' ? 'voice' : 'ink';
  } catch {
    return 'ink';
  }
}
const background = ref<HomeBackground>(readBackground());

export function useHomeBackground() {
  function selectBackground(value: HomeBackground) {
    background.value = value;
    try {
      localStorage.setItem(HOME_BACKGROUND_KEY, value);
    } catch {
      // 存储不可用时仍保留当前页面中的选择。
    }
  }
  return { background: readonly(background), selectBackground };
}
