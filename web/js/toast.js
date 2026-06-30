/* 轻量 toast */

import { $ } from "./utils.js";

let timer;

export function toast(msg, icon = "ph-info") {
  const node = $("#toast");
  if (!node) return;
  node.innerHTML = `<i class="ph ${icon}" aria-hidden="true"></i><span></span>`;
  node.querySelector("span").textContent = msg;
  node.hidden = false;
  requestAnimationFrame(() => node.classList.add("is-show"));
  clearTimeout(timer);
  timer = setTimeout(() => {
    node.classList.remove("is-show");
    setTimeout(() => (node.hidden = true), 240);
  }, 2600);
}
