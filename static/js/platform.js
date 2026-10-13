/* Shared shell interactions. No external script dependency. */
(() => {
  'use strict';
  const storage = { get(key) { try { return localStorage.getItem(`guardfall2.${key}`); } catch (_) { return null; } }, set(key, value) { try { localStorage.setItem(`guardfall2.${key}`, value); } catch (_) { /* Storage is optional. */ } } };
  const savedTheme = storage.get('theme');
  document.documentElement.dataset.theme = savedTheme === 'dark' || savedTheme === 'light' ? savedTheme : (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.addEventListener('DOMContentLoaded', () => {
    const themeButton = document.querySelector('.theme-toggle');
    const updateThemeLabel = () => { if (themeButton) { const dark = document.documentElement.dataset.theme === 'dark'; themeButton.setAttribute('aria-label', dark ? '라이트 모드 켜기' : '다크 모드 켜기'); themeButton.setAttribute('aria-pressed', String(dark)); } };
    updateThemeLabel();
    themeButton?.addEventListener('click', () => { document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; storage.set('theme', document.documentElement.dataset.theme); updateThemeLabel(); });
    const sidebar = document.querySelector('.sidebar');
    const toggle = document.querySelector('.menu-toggle');
    const backdrop = document.querySelector('.sidebar-backdrop');
    const close = document.querySelector('.sidebar-close');
    const desktop = window.matchMedia('(min-width: 981px)');
    const setSidebar = (opened, returnFocus = false) => { document.body.classList.toggle('sidebar-open', opened); toggle?.setAttribute('aria-expanded', String(opened)); if (backdrop) backdrop.hidden = !opened; if (sidebar) sidebar.inert = !desktop.matches && !opened; if (opened) close?.focus(); else if (returnFocus) toggle?.focus(); };
    toggle?.addEventListener('click', () => setSidebar(!document.body.classList.contains('sidebar-open')));
    backdrop?.addEventListener('click', () => setSidebar(false, true));
    close?.addEventListener('click', () => setSidebar(false, true));
    document.addEventListener('keydown', event => { if (event.key === 'Escape' && document.body.classList.contains('sidebar-open')) setSidebar(false, true); if (event.key === 'Tab' && document.body.classList.contains('sidebar-open') && sidebar) { const items = [...sidebar.querySelectorAll('a[href], button, summary')].filter(item => item.getClientRects().length); if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1)?.focus(); } else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0]?.focus(); } } });
    desktop.addEventListener('change', () => setSidebar(false));
    setSidebar(false);
    document.querySelectorAll('.nav-section[data-menu-key]').forEach(section => { const key = `menu.${section.dataset.menuKey}`; const state = storage.get(key); if (state !== null) section.open = state === 'open'; section.addEventListener('toggle', () => storage.set(key, section.open ? 'open' : 'closed')); });
    const path = window.location.pathname;
    document.querySelectorAll('.sidebar-navigation a[href], .top-navigation a[href]').forEach(link => { if (link.getAttribute('href') === path) { link.classList.add('active'); link.setAttribute('aria-current', 'page'); let ancestor = link.parentElement; while (ancestor && ancestor !== sidebar) { if (ancestor.tagName === 'DETAILS') ancestor.open = true; ancestor = ancestor.parentElement; } } });
    document.addEventListener('click', event => { document.querySelectorAll('.profile-menu[open]').forEach(menu => { if (!menu.contains(event.target)) menu.open = false; }); });
  });
})();
