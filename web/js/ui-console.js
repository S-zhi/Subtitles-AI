/* 任务控制台：参数初始化 + URL 校验 + 提交 */

import { $, el } from "./utils.js";
import { createTask } from "./store.js";
import { toast } from "./toast.js";
import { Api } from "./api.js";
import { LANG_LABEL } from "./constants.js";

const CFG = window.APP_CONFIG;
const FALLBACK_LANGUAGES = ["en", "zh", "de", "es", "ru", "ko", "fr", "ja"];
const FALLBACK_MODELS = [
  "tiny.en", "tiny", "base.en", "base", "small.en",
  "small", "medium.en", "medium", "large-v1", "large-v2",
];
const DEFAULT_SOURCE_LANGUAGE = "en";
const LANGUAGE_DISPLAY = typeof Intl !== "undefined" && Intl.DisplayNames
  ? new Intl.DisplayNames(["zh-CN"], { type: "language" })
  : null;

function initEngines() {
  // 初始化翻译引擎下拉框。
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

function option(value, label = value) {
  // 构造一个 select option 元素。
  const item = el("option");
  item.value = value;
  item.textContent = label;
  return item;
}

function sourceLanguageLabel(code) {
  // 把源语言代码转换为中文展示文案，提交时仍使用原始代码。
  if (LANG_LABEL[code]) return LANG_LABEL[code];
  try {
    return LANGUAGE_DISPLAY?.of(code) || code;
  } catch (e) {
    return code;
  }
}

function renderSourceLanguages(languages) {
  // 渲染源语言下拉框，保留自动检测作为本地特殊选项。
  const sel = $("#sourceLang");
  const current = sel.value || DEFAULT_SOURCE_LANGUAGE;
  sel.innerHTML = "";
  sel.append(option("auto", "自动检测"));
  languages.forEach((code) => {
    sel.append(option(code, sourceLanguageLabel(code)));
  });
  sel.value = [...sel.options].some((item) => item.value === current)
    ? current
    : DEFAULT_SOURCE_LANGUAGE;
}

function modelLabel(model) {
  // 生成 Whisper 模型下拉框展示文案。
  const labels = {
    "tiny.en": "tiny.en · 英语最快",
    tiny: "tiny · 最快",
    "base.en": "base.en · 英语快",
    base: "base · 快",
    "small.en": "small.en · 英语推荐",
    small: "small · 推荐",
    "medium.en": "medium.en · 英语较准",
    medium: "medium · 较准",
    "large-v1": "large-v1 · 高精度",
    "large-v2": "large-v2 · 高精度",
  };
  return labels[model] || model;
}

function renderModelWeights(models) {
  // 渲染 Whisper 模型权重下拉框。
  const sel = $("#model");
  const current = sel.value || "small";
  sel.innerHTML = "";
  models.forEach((model) => {
    sel.append(option(model, modelLabel(model)));
  });
  sel.value = [...sel.options].some((item) => item.value === current) ? current : "small";
}

async function initSrtOptions() {
  // 从后端加载源语言和模型权重选项，失败时使用本地兜底。
  renderSourceLanguages(FALLBACK_LANGUAGES);
  renderModelWeights(FALLBACK_MODELS);

  try {
    const [languages, models] = await Promise.all([
      Api.listVideoLanguages(),
      Api.listModelWeights(),
    ]);
    renderSourceLanguages(languages);
    renderModelWeights(models);
  } catch (err) {
    toast(err.message || "获取识别选项失败，已使用默认选项", "ph-warning-circle");
  }
}

export function initConsole() {
  // 初始化控制台表单交互。
  initEngines();
  initSrtOptions();

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
