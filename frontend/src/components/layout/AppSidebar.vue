<template>
  <aside
    class="sidebar"
    :class="[
      collapsed ? 'w-[72px]' : 'w-56',
      { '-translate-x-full lg:translate-x-0': !mobileOpen },
    ]"
  >
    <div class="sidebar-header" :class="{ 'px-4': collapsed }">
      <div class="flex h-9 w-9 items-center justify-center overflow-hidden rounded-xl shadow-glow">
        <img src="/logo.svg" alt="EasyMail" class="h-full w-full object-contain" />
      </div>
      <div v-if="!collapsed" class="min-w-0">
        <div class="truncate text-lg font-bold text-gray-900 dark:text-white">
          {{ siteConfig.siteName }}
        </div>
        <div class="text-xs text-gray-400 dark:text-dark-500">IMAP Mail Manager</div>
      </div>
    </div>

    <nav class="sidebar-nav scrollbar-hide">
      <RouterLink
        v-for="item in items"
        :key="item.to"
        :to="item.to"
        class="sidebar-link mb-1"
        :class="{ 'sidebar-link-active': route.path === item.to, 'justify-center px-0': collapsed }"
        :title="collapsed ? item.label : undefined"
        @click="$emit('close-mobile')"
      >
        <Icon :name="item.icon" size="md" class="flex-shrink-0" />
        <span v-if="!collapsed">{{ item.label }}</span>
      </RouterLink>
    </nav>

    <div class="mt-auto border-t border-gray-100 p-3 dark:border-dark-800">
      <button
        class="sidebar-link w-full"
        :class="{ 'justify-center px-0': collapsed }"
        @click="$emit('toggle-collapse')"
      >
        <Icon :name="collapsed ? 'arrowRight' : 'chevronDown'" />
        <span v-if="!collapsed">{{ collapsed ? '展开侧栏' : '收起侧栏' }}</span>
      </button>
    </div>
  </aside>

  <transition name="fade">
    <div
      v-if="mobileOpen"
      class="fixed inset-0 z-30 bg-black/50 lg:hidden"
      @click="$emit('close-mobile')"
    ></div>
  </transition>
</template>

<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import Icon from '@/components/common/Icon.vue'
import { siteConfig } from '@/config'

defineProps<{
  collapsed: boolean
  mobileOpen: boolean
}>()

defineEmits<{
  (event: 'toggle-collapse'): void
  (event: 'close-mobile'): void
}>()

const route = useRoute()

const items = [
  { to: '/dashboard', label: '后台面板', icon: 'dashboard' },
  { to: '/settings', label: '系统设置', icon: 'settings' },
]
</script>
