/* 任务控制台：参数初始化 + URL 校验 + 提交 */

import { $, el } from "./utils.js";
import { createTask } from "./store.js";
import { toast } from "./toast.js";

const CFG = window.APP_CONFIG;

function initEngines() {
  const sel = $("#engine");
  sel.innerHTML = "";
  CFG.TRANSLATION_ENGINES.forEach((e) => {
    const o = el("option");
    o.value = e.value;
    o.textContent = e.enabled ? e.label : e.label + "（暂未开放）";
    o.disabled = !e.enabled;
    sel.append(o);
  });
  const first = CFG.TRANSLATION_ENGINES.find((e) => e.enabled);
  if (first) sel.value = first.value;
}

export function initConsole() {
  initEngines();

  const form = $("#taskForm");
  const urlInput = $("#url");
  const hint = $("#urlHint");
  const bar = $("#consoleBar");
  const submitBtn = $("#submitBtn");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = urlInput.value.trim();

    bar.classList.remove("is-error");
    hint.classList.remove("is-error");
    if (!url || !/^https?:\/\/.+/i.test(url)) {
      bar.classList.add("is-error");
      hint.classList.add("is-error");
      hint.textContent = "请输入有效的视频链接（以 http(s):// 开头）";
      urlInput.focus();
      return;
    }
    hint.textContent = "粘贴单个视频页面地址，回车或点击开始处理";

    const payload = {
      url,
      sourceLang: $("#sourceLang").value,
      targetLang: $("#targetLang").value,
      mode: form.elements.mode.value,
      burn: form.elements.burn.value,
      model: $("#model").value,
      engine: $("#engine").value,
    };

    submitBtn.disabled = true;
    try {
      await createTask(payload);
      toast("任务已加入队列", "ph-check-circle");
      urlInput.value = "";
    } catch (err) {
      toast(err.message || "创建任务失败", "ph-warning-circle");
    } finally {
      submitBtn.disabled = false;
    }
  });
}
