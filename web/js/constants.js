/* 共享常量：与后端状态机一致 */

export const STEPS = [
  { key: "DOWNLOADING", label: "下载" },
  { key: "EXTRACTING", label: "提取" },
  { key: "TRANSCRIBING", label: "识别" },
  { key: "TRANSLATING", label: "翻译" },
  { key: "BURNING", label: "烧录" },
];
export const STEP_KEYS = STEPS.map((s) => s.key);

export const STATUS_META = {
  PENDING: { label: "排队中", cls: "pending", icon: "ph-clock" },
  DOWNLOADING: { label: "下载视频", cls: "active", icon: "ph-spinner" },
  EXTRACTING: { label: "提取音频", cls: "active", icon: "ph-spinner" },
  TRANSCRIBING: { label: "语音识别", cls: "active", icon: "ph-spinner" },
  TRANSLATING: { label: "翻译字幕", cls: "active", icon: "ph-spinner" },
  BURNING: { label: "烧录字幕", cls: "active", icon: "ph-spinner" },
  SUCCESS: { label: "已完成", cls: "success", icon: "ph-check" },
  FAILED: { label: "失败", cls: "failed", icon: "ph-warning" },
};

export const LANG_LABEL = {
  auto: "自动检测",
  "zh-CN": "简体中文",
  "zh-TW": "繁体中文",
  zh: "中文",
  en: "英语",
  ja: "日语",
  ko: "韩语",
};

export const TERMINAL = new Set(["SUCCESS", "FAILED"]);
