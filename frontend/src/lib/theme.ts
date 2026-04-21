const STORAGE_KEY = 'easymail-theme'

export function isDarkTheme(): boolean {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'dark') {
    return true
  }
  if (stored === 'light') {
    return false
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function applyStoredTheme() {
  document.documentElement.classList.toggle('dark', isDarkTheme())
}

export function toggleTheme() {
  const dark = !document.documentElement.classList.contains('dark')
  localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light')
  document.documentElement.classList.toggle('dark', dark)
  return dark
}
