/* 药脉 · 今日页。无依赖，直接操作 DOM，数据来自 ./data/items.json。 */
"use strict";

const DATA_URL = "./data/items.json";
const DIMENSIONS = ["D1", "D2", "D3", "D4", "D5", "D6"];

const state = {
  data: null,
  dim: "all",
  index: 0,
};

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function normalizeDimension(value) {
  const dim = String(value || "").toUpperCase();
  return DIMENSIONS.includes(dim) ? dim : "D6";
}

function trim(value) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeData(data) {
  if (!data || typeof data !== "object") throw new Error("数据不是有效的 JSON 对象");
  if (!Array.isArray(data.days)) throw new Error("数据结构缺少 days 数组");
  return data;
}

/* ---------- 读取数据 ---------- */

function loadData() {
  // 先尝试 fetch；直接以 file:// 打开时部分浏览器会拦截，
  // 再退回 XMLHttpRequest（部分浏览器允许同目录读取）。
  return fetch(DATA_URL, { cache: "no-store" })
    .then((res) => {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.text().then((text) => JSON.parse(text));
    })
    .catch(
      () =>
        new Promise((resolve, reject) => {
          let xhr;
          try {
            xhr = new XMLHttpRequest();
          } catch (err) {
            reject(new Error("无法读取 " + DATA_URL));
            return;
          }
          xhr.open("GET", DATA_URL, true);
          xhr.onload = () => {
            if (xhr.status === 0 || (xhr.status >= 200 && xhr.status < 300)) {
              try {
                resolve(JSON.parse(xhr.responseText));
              } catch (err) {
                reject(new Error("JSON 解析失败：" + err.message));
              }
            } else {
              reject(new Error("HTTP " + xhr.status));
            }
          };
          xhr.onerror = () => reject(new Error("无法读取 " + DATA_URL + "（本地文件访问可能被浏览器拦截）"));
          try {
            xhr.send();
          } catch (err) {
            reject(err);
          }
        })
    );
}

/* ---------- 渲染 ---------- */

function mBadge(value) {
  const m = Math.min(5, Math.max(1, Math.round(Number(value) || 1)));
  const wrap = el("span", "m-badge");
  wrap.title = "材料性 M" + m;
  wrap.appendChild(el("span", "m-text", "M" + m));
  const dots = el("span", "m-dots");
  dots.setAttribute("aria-hidden", "true");
  for (let i = 1; i <= 5; i += 1) {
    dots.appendChild(el("span", i <= m ? "dot on" : "dot", "●"));
  }
  wrap.appendChild(dots);
  return wrap;
}

function card(item, isMust) {
  const dim = normalizeDimension(item.dimension);
  const node = el("a", "card dim-" + dim.toLowerCase() + (isMust ? " card-must" : ""));
  node.href = item.url || "#";
  node.target = "_blank";
  node.rel = "noopener";

  const head = el("div", "card-head");
  head.appendChild(el("span", "dim-badge", dim));
  head.appendChild(mBadge(item.m));
  if (trim(item.source)) head.appendChild(el("span", "source", item.source));
  if (trim(item.event_type)) head.appendChild(el("span", "event", item.event_type));
  node.appendChild(head);

  const titleZh = trim(item.title_zh);
  const title = titleZh || trim(item.title) || "(无标题)";
  node.appendChild(el("h3", "card-title", title));
  if (titleZh && trim(item.title) && item.title !== titleZh) {
    node.appendChild(el("p", "card-orig", item.title));
  }
  if (trim(item.why)) node.appendChild(el("p", "card-why", item.why));
  return node;
}

function visibleItems(day) {
  const items = Array.isArray(day.items) ? day.items : [];
  if (state.dim === "all") return items;
  return items.filter((item) => normalizeDimension(item.dimension) === state.dim);
}

function updateDayNav(day) {
  const days = state.data && Array.isArray(state.data.days) ? state.data.days : [];
  const idx = days.findIndex((d) => d && d.date === day.date);
  const nav = document.getElementById("day-nav");
  const current = document.getElementById("current-date");
  const prev = document.getElementById("prev-day");
  const next = document.getElementById("next-day");

  if (current) current.textContent = day.date || "";
  if (nav) nav.hidden = days.length < 2 || idx < 0;

  if (prev) {
    const older = idx >= 0 && idx + 1 < days.length ? days[idx + 1] : null;
    prev.disabled = !older;
    prev.textContent = older ? "← " + older.date : "← 前一天";
  }
  if (next) {
    const newer = idx > 0 ? days[idx - 1] : null;
    next.disabled = !newer;
    next.textContent = newer ? newer.date + " →" : "后一天 →";
  }
}

function renderDay(dayData) {
  const app = document.getElementById("app");
  if (!app) return;
  if (!dayData || typeof dayData !== "object") {
    renderNotice("没有可显示的日期数据。", "");
    return;
  }

  const days = state.data && Array.isArray(state.data.days) ? state.data.days : [];
  const idx = days.findIndex((d) => d && d.date === dayData.date);
  if (idx >= 0) state.index = idx;

  const items = visibleItems(dayData);
  const mustIds = Array.isArray(dayData.must) ? dayData.must : [];
  const mustItems = items.filter((item) => mustIds.includes(item.id));

  const section = el("section", "day");
  section.dataset.date = dayData.date || "";
  section.appendChild(el("h2", "day-title", dayData.date || "未知日期"));

  const mustSection = el("section", "must-section");
  mustSection.appendChild(el("h3", "section-title", "必看"));
  if (mustItems.length) {
    const grid = el("div", "must-grid");
    mustItems.forEach((item) => grid.appendChild(card(item, true)));
    mustSection.appendChild(grid);
  } else {
    mustSection.appendChild(el("p", "quiet", "今日无必看"));
  }
  section.appendChild(mustSection);

  const listSection = el("section", "all-section");
  listSection.appendChild(el("h3", "section-title", "全部条目"));
  if (items.length) {
    const list = el("div", "list");
    items.forEach((item) => list.appendChild(card(item, false)));
    listSection.appendChild(list);
  } else {
    listSection.appendChild(
      el("p", "quiet", state.dim === "all" ? "本期无条目" : "该维度下本期无条目")
    );
  }
  section.appendChild(listSection);

  app.textContent = "";
  app.appendChild(section);
  updateDayNav(dayData);
}

function renderNotice(title, detail) {
  const app = document.getElementById("app");
  if (!app) return;
  app.textContent = "";
  const box = el("div", "notice");
  box.appendChild(el("p", "notice-title", title));
  if (detail) box.appendChild(el("p", "notice-detail", detail));

  if (window.location.protocol === "file:") {
    box.appendChild(
      el(
        "p",
        "notice-hint",
        "浏览器默认会拦截 file:// 页面读取本地文件。你可以在下方选择项目中的 data/items.json，或运行 python3 -m http.server 8765 后访问 http://localhost:8765/。"
      )
    );
    const pick = el("label", "file-pick", "选择 data/items.json");
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json,application/json";
    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          start(JSON.parse(String(reader.result)));
        } catch (err) {
          renderNotice("无法解析所选文件。", err.message);
        }
      };
      reader.onerror = () => renderNotice("读取所选文件失败。", "请重试或改用本地服务器。");
      reader.readAsText(file);
    });
    pick.appendChild(input);
    box.appendChild(pick);
  } else {
    box.appendChild(
      el("p", "notice-hint", "请确认 data/items.json 存在并且是合法 JSON，然后刷新页面。")
    );
  }
  app.appendChild(box);
}

function renderCurrentDay() {
  const days = state.data && Array.isArray(state.data.days) ? state.data.days : [];
  if (!days.length) {
    renderNotice("数据中没有可显示的日期。", "");
    return;
  }
  if (state.index < 0 || state.index >= days.length) state.index = 0;
  renderDay(days[state.index]);
}

function start(data) {
  state.data = normalizeData(data);
  state.index = 0;
  const generated = document.getElementById("generated");
  if (generated) {
    generated.textContent = state.data.generated_at ? "更新于 " + state.data.generated_at : "";
  }
  renderCurrentDay();
}

async function load() {
  const app = document.getElementById("app");
  if (app) {
    app.textContent = "";
    app.appendChild(el("p", "quiet", "正在加载今日简报…"));
  }
  try {
    start(await loadData());
  } catch (err) {
    renderNotice(
      "无法显示今日简报：读取 " + DATA_URL + " 失败。",
      err && err.message ? err.message : String(err)
    );
  }
}

/* ---------- 交互 ---------- */

function setDim(dim) {
  state.dim = dim;
  document.querySelectorAll(".tab").forEach((btn) => {
    const on = btn.dataset.dim === dim;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
  if (state.data) renderCurrentDay();
}

function stepDay(offset) {
  const days = state.data && Array.isArray(state.data.days) ? state.data.days : [];
  const target = state.index + offset;
  if (target < 0 || target >= days.length) return;
  state.index = target;
  renderDay(days[target]);
}

function bind() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => setDim(btn.dataset.dim));
  });
  const prev = document.getElementById("prev-day");
  const next = document.getElementById("next-day");
  if (prev) prev.addEventListener("click", () => stepDay(1));
  if (next) next.addEventListener("click", () => stepDay(-1));
}

window.renderDay = renderDay;

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    bind();
    load();
  });
} else {
  bind();
  load();
}
