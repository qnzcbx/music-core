import { createRouter, createWebHistory } from 'vue-router';
const SettingsView = () => import('../views/SettingsView.vue');
import HomeView from '../views/HomeView.vue';
import SearchView from '../views/SearchView.vue';
const PlayerView = () => import('../views/PlayerView.vue');
const DownloadsView = () => import('../views/DownloadsView.vue');

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
      beforeEnter: (to) => (to.query.q ? { path: '/search', query: to.query } : true),
    },
    { path: '/search', component: SearchView },
    { path: '/player/:id', component: PlayerView },
    { path: '/player', component: PlayerView },
    { path: '/downloads', component: DownloadsView },
    { path: '/settings', component: SettingsView },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('../views/NotFoundView.vue'),
      meta: { hideEmptyPlayer: true },
    },
  ],
});

// 刷新沉浸地址时回到浏览页，恢复播放器只呈现在底栏。
router.beforeEach((to, from) => {
  if (
    !from.matched.length &&
    to.matched.some((record) => record.path === '/player' || record.path === '/player/:id')
  )
    return '/';
});
