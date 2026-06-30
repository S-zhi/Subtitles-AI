/* 外壳：侧边导航 / 视图切换 / 筛选 / 环境标识，全部由 store 状态驱动。 */

import { $, $$ } from "./utils.js";
import { state, subscribe, setView, setFilter } from "./store.js";
import { USE_MOCK } from "./api.js";

export function initShell() {
  $("#nav").addEventListener("click", (e) => {
    const item = e.target.closest(".nav__item");
    if (item) setView(item.dataset.view);
  });

  $("#filters").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (chip) setFilter(chip.dataset.filter);
  });

  const pill = $("#envPill");
  if (USE_MOCK) {
    pill.textContent = "示例数据";
    pill.dataset.mode = "mock";
  } else {
    pill.textContent = "已连接后端";
    pill.dataset.mode = "live";
  }

  subscribe(syncShell);
  syncShell();
}

function syncShell() {
  $$(".view").forEach((v) => v.classList.toggle("is-active", v.dataset.view === state.view));
  $$(".nav__item").forEach((n) => n.classList.toggle("is-active", n.dataset.view === state.view));
  $$("#filters .chip").forEach((c) => c.classList.toggle("is-active", c.dataset.filter === state.filter));
}
