<script setup lang="ts">
import { RouterLink } from "vue-router";
import OpenIcon from "~icons/lucide/panel-left-open";
import CloseIcon from "~icons/lucide/panel-left-close";
import { navigation } from "./navigation";

defineProps<{ expanded: boolean; searchQuery: string }>();
defineEmits<{ toggle: [] }>();
</script>
<template>
  <aside class="app-sidebar" aria-label="应用导航" :data-expanded="expanded">
    <RouterLink to="/" class="shell-brand" aria-label="拾音 首页" title="拾音 首页">
      <span class="shell-brand-icon" aria-hidden="true"></span>
      <span class="sidebar-label wordmark">拾音</span>
    </RouterLink>
    <nav aria-label="主导航">
      <RouterLink
        v-for="item in navigation.filter((row) => row.to !== '/settings')"
        :key="item.to"
        :to="
          item.to === '/search' && searchQuery
            ? { path: item.to, query: { q: searchQuery } }
            : item.to
        "
        :title="item.label"
        :aria-label="item.label"
        class="sidebar-link"
      >
        <component :is="item.icon" aria-hidden="true" />
        <span class="sidebar-label">{{ item.label }}</span>
      </RouterLink>
    </nav>
    <div class="sidebar-foot">
      <span class="sidebar-label sidebar-caption">留一点时间，给音乐。</span>
      <RouterLink to="/settings" class="sidebar-link" aria-label="设置" title="设置">
        <component
          :is="navigation.find((row) => row.to === '/settings')!.icon"
          aria-hidden="true"
        />
        <span class="sidebar-label">设置</span>
      </RouterLink>
      <button
        type="button"
        class="sidebar-toggle"
        :aria-label="expanded ? '收起侧栏' : '展开侧栏'"
        :title="expanded ? '收起侧栏' : '展开侧栏'"
        :aria-expanded="expanded"
        @click="$emit('toggle')"
      >
        <component :is="expanded ? CloseIcon : OpenIcon" aria-hidden="true" />
        <span class="sidebar-label">收起侧栏</span>
      </button>
    </div>
  </aside>
</template>
<style scoped>
.app-sidebar {
  --sidebar-icon-slot: 28px;
  --sidebar-label-gap: 14px;

  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  max-height: none;
  padding: 24px 12px 16px;
  border-left: 0;
  border-right: 1px solid var(--app-border-soft);
  background: var(--app-sidebar);
  overflow-x: hidden;
  overflow-y: auto;
}

.shell-brand,
.sidebar-link,
.sidebar-toggle {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: center;
  box-sizing: border-box;
  min-width: 0;
  min-height: 46px;
  padding: 12px;
  border-radius: 10px;
  color: var(--app-text-muted);
  text-align: left;
  text-decoration: none;
  white-space: nowrap;
}

/* 展开时统一图标列宽，文字从同一位置开始。 */
.app-sidebar[data-expanded="true"]
  :is(.shell-brand, .sidebar-link, .sidebar-toggle) {
  grid-template-columns: var(--sidebar-icon-slot) minmax(0, 1fr);
  column-gap: var(--sidebar-label-gap);
}

/* 展开时在图标列内居中，收起时在整行内居中。 */
.shell-brand-icon,
.sidebar-link > svg,
.sidebar-toggle > svg {
  justify-self: center;
}

.sidebar-link > svg,
.sidebar-toggle > svg {
  width: 20px;
  height: 20px;
}

.shell-brand {
  margin-bottom: 48px;
  color: var(--app-link);
}

.shell-brand-icon {
  width: var(--sidebar-icon-slot);
  height: var(--sidebar-icon-slot);
  background: currentColor;
  mask: url("/shiyin-icon-mono.svg") center / contain no-repeat;
  /* 双手的视觉重心偏下，只微调图标，不移动整行。 */
  transform: translateY(-1px);
}

.shell-brand .wordmark {
  font-size: 22px;
  line-height: 1.15;
}

nav {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-width: 0;
  gap: 10px;
}

.sidebar-link {
  font-size: 13px;
}

.sidebar-link:hover,
.sidebar-toggle:hover {
  background: var(--app-hover);
  color: var(--app-link);
}

.sidebar-link.router-link-exact-active {
  background: var(--app-surface-raised);
  color: var(--app-link);
  box-shadow: 0 2px 9px var(--app-shadow-soft);
}

.sidebar-label {
  min-width: 0;
  max-width: 0;
  overflow: hidden;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.18s;
}

/* 收起时不让文字形成额外的 Grid 行。 */
.app-sidebar:not([data-expanded="true"])
  :is(.shell-brand, .sidebar-link, .sidebar-toggle) > .sidebar-label {
  display: none;
}

.app-sidebar[data-expanded="true"] .sidebar-label {
  max-width: 170px;
  opacity: 1;
  visibility: visible;
}

.sidebar-foot {
  margin-top: auto;
  padding-top: 32px;
}

.sidebar-caption {
  display: block;
  margin: 0 14px 20px;
  color: var(--app-text-soft);
  font-size: 11px;
  white-space: nowrap;
}

.sidebar-toggle {
  width: 100%;
  border: 0;
  background: transparent;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

a:focus-visible,
button:focus-visible {
  outline: 2px solid var(--app-focus);
  outline-offset: -2px;
}

@media (max-width: 600px) {
  .app-sidebar {
    padding: 16px 4px 10px;
  }

  .shell-brand {
    margin-bottom: 30px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sidebar-label {
    transition: none;
  }
}
</style>
