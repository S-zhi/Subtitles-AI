/* 浅色 / 深色主题切换（跟随系统，可手动覆盖） */

import { $ } from "./utils.js";

const KEY = "subtrans_theme";

function isDark(root) {
  const t = root.getAttribute("data-theme");
  return t === "dark" || (t === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
}

export function initTheme() {
  const btn = $("#themeToggle");
  const root = document.documentElement;

  let saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  if (saved) root.setAttribute("data-theme", saved);

  const syncIcon = () => {
    btn.innerHTML = `<i class="ph ${isDark(root) ? "ph-sun" : "ph-moon"}" aria-hidden="true"></i>`;
  };
  syncIcon();

  btn.addEventListener("click", () => {
    const next = isDark(root) ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem(KEY, next); } catch (e) {}
    syncIcon();
  });
}
