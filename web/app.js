/* ============================================================
   字幕翻译工作台 - 前端逻辑（纯 JS，无框架）
   数据层抽象为 Api，mock 与真实接口可一键切换。
   ============================================================ */

(() => {
  "use strict";

  const CFG = window.APP_CONFIG;

  /* ---------- 常量：流水线步骤 ---------- */
  // 顺序固定，与后端状态机一致
  const STEPS = [
    { key: "DOWNLOADING", label: "下载视频" },
    { key: "EXTRACTING", label: "提取音频" },
    { key: "TRANSCRIBING", label: "语音识别" },
    { key: "TRANSLATING", label: "翻译字幕" },
    { key: "BURNING", label: "烧录字幕" },
  ];
  const STEP_KEYS = STEPS.map((s) => s.key);

  const STATUS_META = {
    PENDING: { label: "排队中", cls: "pending", icon: "ph-hourglass" },
    DOWNLOADING: { label: "下载视频", cls: "active", icon: "ph-download-simple" },
    EXTRACTING: { label: "提取音频", cls: "active", icon: "ph-waveform" },
    TRANSCRIBING: { label: "语音识别", cls: "active", icon: "ph-microphone" },
    TRANSLATING: { label: "翻译字幕", cls: "active", icon: "ph-translate" },
    BURNING: { label: "烧录字幕", cls: "active", icon: "ph-film-strip" },
    SUCCESS: { label: "已完成", cls: "success", icon: "ph-check-circle" },
    FAILED: { label: "失败", cls: "failed", icon: "ph-warning-circle" },
  };

  const LANG_LABEL = {
    auto: "自动检测",
    "zh-CN": "简体中文",
    "zh-TW": "繁体中文",
    zh: "中文",
    en: "英语",
    ja: "日语",
    ko: "韩语",
  };

  const TERMINAL = new Set(["SUCCESS", "FAILED"]);

  /* ---------- 工具函数 ---------- */
  const $ = (sel, root = document) => root.querySelector(sel);
  const el = (tag, cls) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    return n;
  };
  const uid = () => "task_" + Math.random().toString(36).slice(2, 9);
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

  function progressToStepIndex(progress) {
    return clamp(Math.floor(progress / (100 / STEPS.length)), 0, STEPS.length - 1);
  }

  function statusForProgress(progress) {
    if (progress >= 100) return "SUCCESS";
    if (progress <= 0) return "PENDING";
    return STEP_KEYS[progressToStepIndex(progress)];
  }

  function shortUrl(url) {
    try {
      const u = new URL(url);
      const tail = (u.pathname + u.search).replace(/\/$/, "");
      const t = tail.length > 28 ? tail.slice(0, 14) + "…" + tail.slice(-10) : tail;
      return u.host + t;
    } catch (e) {
      return url.length > 46 ? url.slice(0, 30) + "…" + url.slice(-12) : url;
    }
  }

  function relTime(ts) {
    const s = Math.floor((Date.now() - ts) / 1000);
    if (s < 60) return "刚刚";
    if (s < 3600) return Math.floor(s / 60) + " 分钟前";
    if (s < 86400) return Math.floor(s / 3600) + " 小时前";
    return Math.floor(s / 86400) + " 天前";
  }

  /* ============================================================
     数据层：真实接口（REST + SSE）
     后端就绪后启用（USE_MOCK=false）
     ============================================================ */
  const RealApi = {
    base: CFG.API_BASE_URL,

    async createTask(payload) {
      const res = await fetch(`${this.base}/api/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("创建任务失败：" + res.status);
      return res.json();
    },

    async listTasks() {
      const res = await fetch(`${this.base}/api/tasks`);
      if (!res.ok) throw new Error("获取任务列表失败：" + res.status);
      return res.json();
    },

    async deleteTask(id) {
      const res = await fetch(`${this.base}/api/tasks/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("删除失败：" + res.status);
    },

    async retryTask(id) {
      const res = await fetch(`${this.base}/api/tasks/${id}/retry`, { method: "POST" });
      if (!res.ok) throw new Error("重试失败：" + res.status);
      return res.json();
    },

    // 通过 SSE 订阅单任务进度，返回取消函数
    subscribeProgress(id, onUpdate) {
      const es = new EventSource(`${this.base}/api/tasks/${id}/stream`);
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          onUpdate(data);
          if (TERMINAL.has(data.status)) es.close();
        } catch (_) {}
      };
      es.onerror = () => es.close();
      return () => es.close();
    },

    downloadUrl(id, kind) {
      return kind === "subtitle"
        ? `${this.base}/api/tasks/${id}/subtitle`
        : `${this.base}/api/tasks/${id}/download`;
    },
  };

  /* ============================================================
     数据层：Mock（自动模拟整条流水线）
     ============================================================ */
  const MockApi = (() => {
    const STORE_KEY = "subtrans_mock_tasks_v1";

    function seed() {
      const now = Date.now();
      return [
        {
          id: uid(),
          url: "https://example.com/watch?v=demo-finished",
          title: "示例视频 · 已完成",
          sourceLang: "en",
          targetLang: "zh-CN",
          mode: "bilingual",
          burn: "hard",
          model: "small",
          engine: "deepseek",
          status: "SUCCESS",
          progress: 100,
          error: null,
          createdAt: now - 1000 * 60 * 42,
          outputs: { video: "#mock-video", subtitle: "#mock-srt" },
          _sim: false,
        },
        {
          id: uid(),
          url: "https://example.com/watch?v=demo-running",
          title: null,
          sourceLang: "auto",
          targetLang: "zh-CN",
          mode: "mono",
          burn: "hard",
          model: "small",
          engine: "deepseek",
          status: "TRANSCRIBING",
          progress: 48,
          error: null,
          createdAt: now - 1000 * 90,
          outputs: null,
          _sim: true,
        },
        {
          id: uid(),
          url: "https://example.com/watch?v=demo-failed",
          title: null,
          sourceLang: "auto",
          targetLang: "ja",
          mode: "mono",
          burn: "soft",
          model: "medium",
          engine: "deepseek",
          status: "FAILED",
          progress: 22,
          error: "下载失败：无法解析视频地址（示例错误）",
          createdAt: now - 1000 * 60 * 8,
          outputs: null,
          _sim: false,
        },
      ];
    }

    let tasks;
    try {
      const raw = localStorage.getItem(STORE_KEY);
      tasks = raw ? JSON.parse(raw) : seed();
    } catch (e) {
      tasks = seed();
    }

    const persist = () => {
      try {
        localStorage.setItem(STORE_KEY, JSON.stringify(tasks));
      } catch (e) {}
    };

    const find = (id) => tasks.find((t) => t.id === id);
    const delay = (ms) => new Promise((r) => setTimeout(r, ms));

    return {
      async createTask(payload) {
        const t = {
          id: uid(),
          url: payload.url,
          title: null,
          sourceLang: payload.sourceLang,
          targetLang: payload.targetLang,
          mode: payload.mode,
          burn: payload.burn,
          model: payload.model,
          engine: payload.engine,
          status: "PENDING",
          progress: 0,
          error: null,
          createdAt: Date.now(),
          outputs: null,
          _sim: true,
        };
        tasks.unshift(t);
        persist();
        await delay(150);
        return { ...t };
      },

      async listTasks() {
        await delay(260); // 模拟网络，触发骨架屏
        return tasks.map((t) => ({ ...t }));
      },

      async deleteTask(id) {
        tasks = tasks.filter((t) => t.id !== id);
        persist();
        await delay(80);
      },

      async retryTask(id) {
        const t = find(id);
        if (t) {
          t.status = "PENDING";
          t.progress = 0;
          t.error = null;
          t._sim = true;
          persist();
        }
        return { ...t };
      },

      // 模拟器：定时推进进度，回调形似 SSE 消息
      subscribeProgress(id, onUpdate) {
        const t = find(id);
        if (!t || !t._sim) return () => {};
        let stopped = false;
        const tick = () => {
          if (stopped) return;
          const inc = 3 + Math.random() * 8;
          t.progress = clamp(t.progress + inc, 0, 100);
          t.status = statusForProgress(t.progress);
          if (t.progress >= 100) {
            t.status = "SUCCESS";
            t.title = "示例视频 · " + shortUrl(t.url);
            t.outputs = { video: "#mock-video", subtitle: "#mock-srt" };
            t._sim = false;
          }
          persist();
          onUpdate({
            id: t.id,
            status: t.status,
            progress: Math.round(t.progress),
            title: t.title,
            outputs: t.outputs,
            error: t.error,
          });
          if (!TERMINAL.has(t.status)) setTimeout(tick, 700 + Math.random() * 500);
        };
        setTimeout(tick, 500);
        return () => {
          stopped = true;
        };
      },

      downloadUrl() {
        return "#";
      },
    };
  })();

  const Api = CFG.USE_MOCK ? MockApi : RealApi;

  /* ============================================================
     视图层
     ============================================================ */
  const taskList = $("#taskList");
  const form = $("#taskForm");
  const submitBtn = $("#submitBtn");
  const filtersEl = $("#filters");
  const toastEl = $("#toast");

  let cache = []; // 当前任务列表快照
  let currentFilter = "all";
  const subscriptions = new Map(); // taskId -> unsubscribe

  function matchesFilter(t) {
    if (currentFilter === "all") return true;
    if (currentFilter === "done") return t.status === "SUCCESS";
    if (currentFilter === "failed") return t.status === "FAILED";
    if (currentFilter === "active") return !TERMINAL.has(t.status);
    return true;
  }

  /* ----- 单个任务卡片 ----- */
  function buildCard(t) {
    const card = el("article", "task");
    card.id = "card-" + t.id;
    card.dataset.id = t.id;

    const meta = STATUS_META[t.status] || STATUS_META.PENDING;
    const isActive = !TERMINAL.has(t.status);

    // 顶部：标题 + 状态 + 删除
    const top = el("div", "task__top");
    const left = el("div");
    const h = el("h3", "task__title");
    h.textContent = t.title || "处理中的视频";
    const url = el("p", "task__url");
    url.textContent = shortUrl(t.url);
    left.append(h, url);

    const right = el("div", "task__right");
    const badge = el("span", `badge badge--${meta.cls}`);
    badge.innerHTML = `<i class="ph ${meta.icon}" aria-hidden="true"></i><span>${meta.label}</span>`;
    const del = el("button", "icon-btn btn--danger-ghost");
    del.type = "button";
    del.setAttribute("aria-label", "删除任务");
    del.innerHTML = `<i class="ph ph-trash" aria-hidden="true"></i>`;
    del.style.width = "32px";
    del.style.height = "32px";
    del.style.fontSize = "16px";
    del.addEventListener("click", () => onDelete(t.id));
    right.append(badge, del);
    top.append(left, right);

    // 元信息标签
    const metaRow = el("div", "task__meta");
    metaRow.append(
      tag(LANG_LABEL[t.sourceLang] + " → " + LANG_LABEL[t.targetLang]),
      tag(t.mode === "bilingual" ? "双语对照" : "仅译文"),
      tag(t.burn === "hard" ? "硬烧录" : "软字幕"),
      tag("whisper:" + t.model),
      tag(t.engine === "deepseek" ? "DeepSeek" : t.engine)
    );

    card.append(top, metaRow);

    // 进度（非失败时展示）
    if (t.status !== "FAILED") {
      const prog = el("div", "task__progress");

      const pm = el("div", "progress-meta");
      const stepText = el("span", "progress-step");
      stepText.innerHTML = isActive
        ? `${meta.label}<span class="dots"></span>`
        : t.status === "SUCCESS"
        ? "处理完成"
        : "等待开始";
      const pct = el("span", "progress-pct");
      pct.textContent = Math.round(t.progress) + "%";
      pm.append(stepText, pct);

      const track = el("div", "progress-track");
      const fill = el(
        "div",
        "progress-fill" + (t.status === "SUCCESS" ? " progress-fill--success" : "")
      );
      fill.style.width = clamp(t.progress, 0, 100) + "%";
      track.append(fill);

      prog.append(pm, track, buildSteps(t));
      card.append(prog);
    } else {
      // 失败：错误提示
      const err = el("div", "task__error");
      err.innerHTML = `<i class="ph ph-warning-circle" aria-hidden="true"></i><span>${
        t.error || "处理失败"
      }</span>`;
      card.append(err);
    }

    // 操作区
    const actions = el("div", "task__actions");
    if (t.status === "SUCCESS") {
      actions.append(
        actionBtn("ph-download-simple", "下载视频", "btn--primary btn--sm", () =>
          download(t, "video")
        ),
        actionBtn("ph-file-text", "下载字幕", "btn--ghost btn--sm", () =>
          download(t, "subtitle")
        )
      );
      card.append(actions);
    } else if (t.status === "FAILED") {
      actions.append(
        actionBtn("ph-arrow-clockwise", "重试", "btn--ghost btn--sm", () => onRetry(t.id))
      );
      card.append(actions);
    }

    return card;
  }

  function tag(text) {
    const s = el("span", "tag");
    s.textContent = text;
    return s;
  }

  function actionBtn(icon, label, cls, onClick) {
    const b = el("button", "btn " + cls);
    b.type = "button";
    b.innerHTML = `<i class="ph ${icon}" aria-hidden="true"></i><span>${label}</span>`;
    b.addEventListener("click", onClick);
    return b;
  }

  function buildSteps(t) {
    const wrap = el("div", "steps");
    const curIdx = t.status === "SUCCESS" ? STEPS.length : progressToStepIndex(t.progress);
    const isActive = !TERMINAL.has(t.status) && t.status !== "PENDING";
    STEPS.forEach((s, i) => {
      const node = el("div", "step");
      if (t.status === "SUCCESS" || i < curIdx) node.classList.add("is-done");
      else if (isActive && i === curIdx) node.classList.add("is-current");
      const bar = el("div", "step__bar");
      const lbl = el("div", "step__label");
      lbl.textContent = s.label;
      node.append(bar, lbl);
      wrap.append(node);
    });
    return wrap;
  }

  /* ----- 整列表渲染 ----- */
  function render() {
    const visible = cache.filter(matchesFilter);
    taskList.innerHTML = "";

    if (visible.length === 0) {
      taskList.append(buildEmpty());
      return;
    }
    visible.forEach((t) => taskList.append(buildCard(t)));
  }

  function buildEmpty() {
    const e = el("div", "empty");
    const hasAny = cache.length > 0;
    e.innerHTML = `
      <div class="empty__icon"><i class="ph ${
        hasAny ? "ph-funnel" : "ph-tray"
      }" aria-hidden="true"></i></div>
      <div class="empty__title">${hasAny ? "该筛选下没有任务" : "还没有任务"}</div>
      <div class="empty__desc">${
        hasAny ? "切换上方筛选查看其它任务" : "在左侧粘贴视频链接，选择翻译选项后开始处理"
      }</div>`;
    return e;
  }

  function renderSkeleton() {
    taskList.innerHTML = "";
    for (let i = 0; i < 3; i++) {
      const s = el("div", "skeleton");
      s.innerHTML = `
        <div class="sk-line" style="width:55%;height:15px"></div>
        <div class="sk-line" style="width:35%;margin-top:10px"></div>
        <div class="sk-line" style="width:100%;height:7px;margin-top:18px"></div>`;
      taskList.append(s);
    }
  }

  /* ----- 局部更新单卡片（进度推送时，避免整列表重绘） ----- */
  function patchCard(update) {
    const idx = cache.findIndex((t) => t.id === update.id);
    if (idx === -1) return;
    cache[idx] = { ...cache[idx], ...update };

    const t = cache[idx];
    if (!matchesFilter(t)) {
      render();
      return;
    }
    const old = $("#card-" + t.id);
    if (old) old.replaceWith(buildCard(t));
    else render();
  }

  /* ============================================================
     交互
     ============================================================ */
  function startTracking(t) {
    if (TERMINAL.has(t.status)) return;
    if (subscriptions.has(t.id)) return;
    const unsub = Api.subscribeProgress(t.id, (update) => {
      patchCard(update);
      if (TERMINAL.has(update.status)) {
        const u = subscriptions.get(t.id);
        if (u) u();
        subscriptions.delete(t.id);
      }
    });
    subscriptions.set(t.id, unsub);
  }

  function stopAllTracking() {
    subscriptions.forEach((unsub) => unsub());
    subscriptions.clear();
  }

  async function onSubmit(e) {
    e.preventDefault();
    const urlInput = $("#url");
    const urlHint = $("#urlHint");
    const url = urlInput.value.trim();

    // 校验
    urlInput.classList.remove("is-error");
    urlHint.classList.remove("is-error");
    if (!url || !/^https?:\/\/.+/i.test(url)) {
      urlInput.classList.add("is-error");
      urlHint.classList.add("is-error");
      urlHint.textContent = "请输入有效的视频链接（以 http(s):// 开头）";
      urlInput.focus();
      return;
    }
    urlHint.textContent = "支持单个视频页面地址";

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
      const t = await Api.createTask(payload);
      cache.unshift(t);
      currentFilter = "all";
      syncFilterUI();
      render();
      startTracking(t);
      toast("任务已创建，开始处理");
      urlInput.value = "";
    } catch (err) {
      toast(err.message || "创建任务失败");
    } finally {
      submitBtn.disabled = false;
    }
  }

  async function onDelete(id) {
    const unsub = subscriptions.get(id);
    if (unsub) unsub();
    subscriptions.delete(id);
    cache = cache.filter((t) => t.id !== id);
    render();
    try {
      await Api.deleteTask(id);
    } catch (err) {
      toast(err.message || "删除失败");
    }
  }

  async function onRetry(id) {
    try {
      const t = await Api.retryTask(id);
      const idx = cache.findIndex((x) => x.id === id);
      if (idx !== -1) cache[idx] = { ...cache[idx], ...t };
      render();
      startTracking(cache[idx]);
      toast("已重新开始处理");
    } catch (err) {
      toast(err.message || "重试失败");
    }
  }

  function download(t, kind) {
    if (CFG.USE_MOCK) {
      toast(kind === "video" ? "示例模式：成品视频下载占位" : "示例模式：字幕文件下载占位");
      return;
    }
    window.open(Api.downloadUrl(t.id, kind), "_blank");
  }

  /* ----- 筛选 ----- */
  function syncFilterUI() {
    filtersEl.querySelectorAll(".chip").forEach((c) => {
      c.classList.toggle("is-active", c.dataset.filter === currentFilter);
    });
  }
  filtersEl.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    currentFilter = chip.dataset.filter;
    syncFilterUI();
    render();
  });

  /* ----- Toast ----- */
  let toastTimer;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    requestAnimationFrame(() => toastEl.classList.add("is-show"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastEl.classList.remove("is-show");
      setTimeout(() => (toastEl.hidden = true), 220);
    }, 2400);
  }

  /* ----- 主题切换 ----- */
  function initTheme() {
    const btn = $("#themeToggle");
    const root = document.documentElement;
    const saved = (() => {
      try {
        return localStorage.getItem("subtrans_theme");
      } catch (e) {
        return null;
      }
    })();
    if (saved) root.setAttribute("data-theme", saved);

    const syncIcon = () => {
      const isDark =
        root.getAttribute("data-theme") === "dark" ||
        (root.getAttribute("data-theme") === "auto" &&
          window.matchMedia("(prefers-color-scheme: dark)").matches);
      btn.innerHTML = `<i class="ph ${isDark ? "ph-sun" : "ph-moon"}" aria-hidden="true"></i>`;
    };
    syncIcon();

    btn.addEventListener("click", () => {
      const cur = root.getAttribute("data-theme");
      const isDark =
        cur === "dark" ||
        (cur === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
      const next = isDark ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem("subtrans_theme", next);
      } catch (e) {}
      syncIcon();
    });
  }

  /* ----- 引擎下拉（来自配置） ----- */
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

  function initEnvPill() {
    const pill = $("#envPill");
    if (CFG.USE_MOCK) {
      pill.textContent = "示例数据";
      pill.dataset.mode = "mock";
    } else {
      pill.textContent = "已连接后端";
      pill.dataset.mode = "live";
    }
  }

  /* ============================================================
     启动
     ============================================================ */
  async function boot() {
    initTheme();
    initEngines();
    initEnvPill();
    form.addEventListener("submit", onSubmit);

    renderSkeleton();
    try {
      cache = await Api.listTasks();
    } catch (err) {
      cache = [];
      toast(err.message || "加载任务失败");
    }
    render();
    cache.forEach(startTracking);

    window.addEventListener("beforeunload", stopAllTracking);
  }

  boot();
})();
