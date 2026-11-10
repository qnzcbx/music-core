import { createRouter, createWebHistory } from 'vue-router';
import SettingsView from '../views/SettingsView.vue';
import HomeView from '../views/HomeView.vue';
import SearchView from '../views/SearchView.vue';
const PlayerView=()=>import('../views/PlayerView.vue');
import DownloadsView from '../views/DownloadsView.vue';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomeView, beforeEnter: to => to.query.q ? { path: '/search', query: to.query } : true },
    { path: '/search', component: SearchView },
    { path: '/player/:id', component: PlayerView },
    { path: '/player', component: PlayerView },
    { path: '/downloads', component: DownloadsView },
    { path: '/settings', component: SettingsView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
});
