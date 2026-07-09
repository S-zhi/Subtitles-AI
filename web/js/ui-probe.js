/* 下载测试页：独立探测单个 URL 是否可解析、可下载。 */

import { $, el, shortUrl } from "./utils.js";
import { Api } from "./api.js";

const URL_RE = /^https?:\/\/.+/i;

function isValidUrl(url) {
  // 判断输入是否是后端探针可接受的 http(s) 页面地址。
  return URL_RE.test(url);
}

function formatDuration(seconds) {
  // 把秒数格式化为紧凑的时长文案。
  if (!Number.isFinite(seconds)) return null;
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function setHint(bar, hint, message, isError = false) {
  // 同步输入栏提示文案和错误样式。
  bar.classList.toggle("is-error", isError);
  hint.classList.toggle("is-error", isError);
  hint.textContent = message;
}

function metaItem(label, value) {
  // 构造一个结果元信息项。
  const item = el("div", "probe-result__meta-item");
  const k = el("span");
  const v = el("strong");
  k.textContent = label;
  v.textContent = value;
  item.append(k, v);
  return item;
}

function renderChecking(resultEl) {
  // 渲染测试中的状态。
  resultEl.className = "probe-result is-checking";
  resultEl.innerHTML = `
    <div class="probe-result__icon"><i class="ph ph-spinner-gap" aria-hidden="true"></i></div>
    <div class="probe-result__body">
      <div class="probe-result__title">测试中</div>
      <div class="probe-result__desc">正在向后端探针确认链接。</div>
    </div>`;
}

function renderResult(resultEl, result, url) {
  // 渲染探针成功或失败的最终结果。
  resultEl.className = `probe-result ${result.ok ? "is-ok" : "is-fail"}`;
  resultEl.replaceChildren();

  const icon = el("div", "probe-result__icon");
  icon.innerHTML = `<i class="ph ${result.ok ? "ph-check-circle" : "ph-warning-circle"}" aria-hidden="true"></i>`;

  const body = el("div", "probe-result__body");
  const title = el("div", "probe-result__title");
  title.textContent = result.ok ? "可以下载" : "暂时不可下载";
  const desc = el("div", "probe-result__desc");
  desc.textContent = result.ok
    ? (result.title || shortUrl(result.webpageUrl || url))
    : (result.reason || result.detail || "yt-dlp 未能确认这个链接");
  body.append(title, desc);

  const meta = el("div", "probe-result__meta");
  const duration = formatDuration(result.duration);
  const webpage = result.webpageUrl || url;
  meta.append(metaItem("链接", shortUrl(webpage)));
  if (result.extractor) meta.append(metaItem("站点解析器", result.extractor));
  if (duration) meta.append(metaItem("时长", duration));
  if (result.ok) meta.append(metaItem("格式数量", String(result.formatsCount || 0)));
  if (!result.ok && result.detail && result.detail !== result.reason) {
    meta.append(metaItem("详情", result.detail));
  }
  body.append(meta);
  resultEl.append(icon, body);
}

async function runProbe(url, refs) {
  // 执行一次探针请求，并把结果同步到页面。
  refs.button.disabled = true;
  setHint(refs.bar, refs.hint, "正在测试链接...");
  renderChecking(refs.result);
  try {
    const result = await Api.probeVideo(url);
    setHint(
      refs.bar,
      refs.hint,
      result.ok ? "测试通过，可以加入任务队列" : "测试失败，请检查链接或 cookies",
      !result.ok,
    );
    renderResult(refs.result, result, url);
  } catch (err) {
    const result = {
      ok: false,
      reason: err.message || "测试失败",
      detail: null,
    };
    setHint(refs.bar, refs.hint, result.reason, true);
    renderResult(refs.result, result, url);
  } finally {
    refs.button.disabled = false;
  }
}

export function initProbe() {
  // 初始化下载测试页表单交互。
  const form = $("#probeForm");
  const input = $("#probeUrl");
  const bar = $("#probeBar");
  const hint = $("#probeHint");
  const button = $("#probeBtn");
  const result = $("#probeResult");

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const url = input.value.trim();
    if (!url || !isValidUrl(url)) {
      setHint(bar, hint, "请输入有效的视频链接（以 http(s):// 开头）", true);
      input.focus();
      return;
    }
    runProbe(url, { bar, hint, button, result });
  });

  input.addEventListener("input", () => {
    if (!input.value.trim()) {
      setHint(bar, hint, "等待输入链接");
    } else {
      setHint(bar, hint, "按开始测试确认可下载性");
    }
  });
}
