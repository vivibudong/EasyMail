<template>
  <svg
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    :class="sizeClass"
    aria-hidden="true"
  >
    <path
      v-if="name === 'mail'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M21.75 7.5v9A2.25 2.25 0 0119.5 18.75h-15A2.25 2.25 0 012.25 16.5v-9m19.5 0A2.25 2.25 0 0019.5 5.25h-15A2.25 2.25 0 002.25 7.5m19.5 0l-8.69 5.518a2.25 2.25 0 01-2.12 0L2.25 7.5"
    />
    <path
      v-else-if="name === 'lock'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M16.5 10.5V7.875a4.5 4.5 0 10-9 0V10.5m-.75 0h10.5A2.25 2.25 0 0119.5 12.75v6A2.25 2.25 0 0117.25 21h-10.5A2.25 2.25 0 014.5 18.75v-6A2.25 2.25 0 016.75 10.5z"
    />
    <path
      v-else-if="name === 'login'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9"
    />
    <path
      v-else-if="name === 'menu'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"
    />
    <path
      v-else-if="name === 'sun'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M12 3v1.5m0 15V21m9-9h-1.5M4.5 12H3m14.864-6.364l-1.06 1.06M7.197 16.803l-1.06 1.06m0-11.227l1.06 1.06m10.607 10.607l1.06 1.06M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"
    />
    <path
      v-else-if="name === 'moon'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"
    />
    <path
      v-else-if="name === 'dashboard'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M3.75 5.25A1.5 1.5 0 015.25 3.75h5.5a1.5 1.5 0 011.5 1.5v5.5a1.5 1.5 0 01-1.5 1.5h-5.5a1.5 1.5 0 01-1.5-1.5zm0 8A1.5 1.5 0 015.25 11.75h5.5a1.5 1.5 0 011.5 1.5v5.5a1.5 1.5 0 01-1.5 1.5h-5.5a1.5 1.5 0 01-1.5-1.5zm8-8a1.5 1.5 0 011.5-1.5h5.5a1.5 1.5 0 011.5 1.5v13.5a1.5 1.5 0 01-1.5 1.5h-5.5a1.5 1.5 0 01-1.5-1.5z"
    />
    <path
      v-else-if="name === 'settings'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M10.5 6h3m-7.5 6h11m-8.25 6h4.5M4.5 3.75h15A1.5 1.5 0 0121 5.25v13.5A1.5 1.5 0 0119.5 20.25h-15A1.5 1.5 0 013 18.75V5.25A1.5 1.5 0 014.5 3.75z"
    />
    <path
      v-else-if="name === 'refresh'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M16.023 9.348h4.992V4.356M7.977 14.652H2.985v4.992m1.27-9.18a8.25 8.25 0 0113.358-3.767l2.41 2.651m-15.758 5.158l2.41 2.651a8.25 8.25 0 0013.358-3.767"
    />
    <path
      v-else-if="name === 'trash'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M6 7.5h12m-10.5 0l.563 10.125A2.25 2.25 0 0010.309 19.5h3.382a2.25 2.25 0 002.246-1.875L16.5 7.5m-6-3h3a1.5 1.5 0 011.5 1.5v1.5h-6V6A1.5 1.5 0 0110.5 4.5z"
    />
    <path
      v-else-if="name === 'logout'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9"
    />
    <path
      v-else-if="name === 'chevronDown'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M19.5 8.25L12 15.75 4.5 8.25"
    />
    <path
      v-else-if="name === 'inbox'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M3.75 7.5h16.5v9.75A2.25 2.25 0 0118 19.5H6a2.25 2.25 0 01-2.25-2.25zm0 0L6 4.5h12l2.25 3m-12 4.5h7.5"
    />
    <path
      v-else-if="name === 'user'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M15.75 6.75a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0"
    />
    <path
      v-else-if="name === 'book'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M12 6.042A8.967 8.967 0 006.75 4.5c-1.757 0-3.43.507-4.854 1.406a.75.75 0 00-.396.65v11.69a.75.75 0 001.148.63A8.976 8.976 0 016.75 17.25c1.74 0 3.37.496 4.75 1.358m.5-12.566A8.967 8.967 0 0117.25 4.5c1.757 0 3.43.507 4.854 1.406a.75.75 0 01.396.65v11.69a.75.75 0 01-1.148.63A8.976 8.976 0 0017.25 17.25c-1.74 0-3.37.496-4.75 1.358"
    />
    <path
      v-else-if="name === 'arrowRight'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3"
    />
    <path
      v-else-if="name === 'shield'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M9 12.75L11.25 15 15 9.75m6-3.75l-8.25-3L4.5 6v5.25c0 5.025 3.42 9.41 8.25 10.56 4.83-1.15 8.25-5.535 8.25-10.56z"
    />
    <path
      v-else-if="name === 'server'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M3.75 6.75A2.25 2.25 0 016 4.5h12a2.25 2.25 0 012.25 2.25v2.25A2.25 2.25 0 0118 11.25H6A2.25 2.25 0 013.75 9zm0 8.25A2.25 2.25 0 016 12.75h12A2.25 2.25 0 0120.25 15v2.25A2.25 2.25 0 0118 19.5H6a2.25 2.25 0 01-2.25-2.25zm3.75-6h.008v.008H7.5V9zm0 8.25h.008v.008H7.5v-.008z"
    />
    <path
      v-else-if="name === 'chart'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M7.5 15V9.75m4.5 5.25V6.75m4.5 8.25v-3m3 8.25H4.5A1.5 1.5 0 013 18.75V4.5"
    />
    <path
      v-else-if="name === 'checkCircle'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M9 12.75l2.25 2.25L15.75 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
    />
    <path
      v-else-if="name === 'xCircle'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
    />
    <path
      v-else-if="name === 'infoCircle'"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M11.25 11.25h1.5v4.5h-1.5zm0-3h1.5v1.5h-1.5zM21 12a9 9 0 11-18 0 9 9 0 0118 0z"
    />
    <path
      v-else-if="name === 'github'"
      fill="currentColor"
      stroke="none"
      d="M12 2C6.477 2 2 6.59 2 12.25c0 4.53 2.865 8.373 6.839 9.727.5.095.682-.222.682-.492 0-.242-.009-.883-.014-1.734-2.782.617-3.37-1.373-3.37-1.373-.454-1.168-1.11-1.48-1.11-1.48-.907-.633.07-.62.07-.62 1.003.073 1.53 1.058 1.53 1.058.892 1.57 2.341 1.117 2.91.854.092-.658.35-1.118.636-1.375-2.22-.26-4.555-1.14-4.555-5.073 0-1.12.39-2.037 1.03-2.755-.104-.26-.447-1.31.097-2.73 0 0 .84-.278 2.75 1.053A9.37 9.37 0 0112 6.966c.85.004 1.706.117 2.504.343 1.91-1.331 2.748-1.053 2.748-1.053.545 1.42.202 2.47.099 2.73.64.718 1.028 1.635 1.028 2.755 0 3.943-2.338 4.809-4.57 5.064.36.318.68.947.68 1.909 0 1.378-.013 2.49-.013 2.827 0 .272.18.593.688.492C19.138 20.62 22 16.778 22 12.25 22 6.59 17.523 2 12 2z"
    />
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    name: string
    size?: 'sm' | 'md' | 'lg'
    strokeWidth?: number
  }>(),
  {
    size: 'md',
    strokeWidth: 1.8,
  },
)

const sizeClass = computed(() => {
  if (props.size === 'sm') return 'h-4 w-4'
  if (props.size === 'lg') return 'h-6 w-6'
  return 'h-5 w-5'
})
</script>
