/* DOM 与格式化工具 */

import { STEPS, STEP_KEYS } from "./constants.js";

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function el(tag, cls) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  return n;
}

export const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
export const uid = () => "task_" + Math.random().toString(36).slice(2, 9);

export const escapeHtml = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export function progressToStepIndex(progress) {
  return clamp(Math.floor(progress / (100 / STEPS.length)), 0, STEPS.length - 1);
}

export function statusForProgress(progress) {
  if (progress >= 100) return "SUCCESS";
  if (progress <= 0) return "PENDING";
  return STEP_KEYS[progressToStepIndex(progress)];
}

export function shortUrl(url) {
  try {
    const u = new URL(url);
    const tail = (u.pathname + u.search).replace(/\/$/, "");
    const t = tail.length > 30 ? tail.slice(0, 16) + "…" + tail.slice(-10) : tail;
    return u.host + t;
  } catch (e) {
    return url.length > 48 ? url.slice(0, 32) + "…" + url.slice(-12) : url;
  }
}
