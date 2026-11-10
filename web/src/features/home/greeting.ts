export const greetings = {
  morning: ['早安，来一首？', '早上好，想听点什么？'],
  noon: ['午安，来首好歌相伴。', '忙里偷闲，也该听一首。'],
  evening: ['晚上好，今天想听什么？', '夜色正好，放首歌吧。'],
  lateNight: ['夜深了，早点休息。', '晚安之前，想听哪一首？'],
  general: ['今天想听什么？', '欢迎回来，有什么想听的？', '从一首歌开始，也很好。'],
};
export function greetingPeriod(hour: number): keyof typeof greetings {
  if (!Number.isFinite(hour) || hour < 0 || hour >= 24) return 'general';
  return hour < 5 || hour >= 23 ? 'lateNight' : hour < 11 ? 'morning' : hour < 17 ? 'noon' : 'evening';
}
/** Called once per Home setup, using browser-local time. No timer or storage. */
export function homeGreeting(date = new Date(), random = Math.random) {
  const period = greetingPeriod(date.getHours());
  const pool = period === 'general' ? greetings.general : [...greetings[period], ...greetings.general];
  return pool[Math.max(0, Math.min(pool.length - 1, Math.floor(random() * pool.length)))]!;
}
