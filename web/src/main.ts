import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './styles/tailwind.css'
import './styles/tokens.css'
import './styles/themes.css'
import { APPEARANCE, startAppearance } from './appearance/theme'
const appearance = startAppearance()
const app = createApp(App).provide(APPEARANCE, appearance).use(router)
app.onUnmount(() => appearance.dispose())
if (import.meta.hot) import.meta.hot.dispose(() => appearance.dispose())
app.mount('#app')
