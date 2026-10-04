export type Theme = 'light' | 'dark';
const preferenceKey = 'jobscore-theme';

export function savedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(preferenceKey);
    return value === 'light' || value === 'dark' ? value : null;
  } catch { return null; }
}

export function initialTheme(): Theme {
  return savedTheme() ?? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}

export function applyTheme(theme: Theme, persist = false) {
  document.documentElement.dataset.theme = theme;
  if (persist) {
    try { localStorage.setItem(preferenceKey, theme); } catch { /* Theme still works without storage. */ }
  }
}

export function watchTheme(onChange: (theme: Theme) => void) {
  const system = matchMedia('(prefers-color-scheme: dark)');
  const sync = () => onChange(initialTheme());
  const systemChanged = () => { if (!savedTheme()) sync(); };
  const storageChanged = (event: StorageEvent) => { if (event.key === preferenceKey || event.key === null) sync(); };
  system.addEventListener('change', systemChanged);
  window.addEventListener('storage', storageChanged);
  return () => {
    system.removeEventListener('change', systemChanged);
    window.removeEventListener('storage', storageChanged);
  };
}
