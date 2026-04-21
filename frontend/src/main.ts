import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { applyStoredTheme } from './lib/theme'
import './style.css'

applyStoredTheme()
document.title = 'EasyMail'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
