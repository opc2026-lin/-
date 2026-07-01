---
title: "homepage"
date: 2026-06-17
tags: [AI, Obsidian, TALOS, 仪表盘, 照明节能, 首页]
type: "system"
status: "draft"
summary: "```dataviewjs // === 导航桥：iframe 内卡片点击 → 在 Obsidian 内打开对应笔记/文件 === if (!window.__talosNavInstalled) { window.__talosNavInstalled = true; wind..."
verified: "unverified"
importance: 2
verifier_type: "auto"
---
```dataviewjs
// === 导航桥：iframe 内卡片点击 → 在 Obsidian 内打开对应笔记/文件 ===
if (!window.__talosNavInstalled) {
  window.__talosNavInstalled = true;
  window.addEventListener("message", async (ev) => {
    const d = ev.data;
    if (!d || d.type !== "talos-open" || !d.path) return;
    const p = d.path;
    try {
      if (p.toLowerCase().endsWith(".html") && app.openWithDefaultApp) {
        app.openWithDefaultApp(p);            // HTML 用系统/内置浏览器打开
      } else {
        await app.workspace.openLinkText(p, "", "tab"); // md 等在新标签打开，保留工作台
      }
    } catch (err) {
      try { await app.workspace.openLinkText(p, "", "tab"); }
      catch (e2) { console.error("talos-open 失败:", p, e2); }
    }
  });
}

// === 实时读取仪表盘 HTML 并注入 iframe ===
// 改成你 vault 内 dashboard.html 的相对路径（相对 vault 根，不含前导 /）。
const path = "dashboard.html";
try {
  const html = await app.vault.adapter.read(path);
  const iframe = document.createElement("iframe");
  iframe.srcdoc = html;
  iframe.style.cssText = "width:100%;height:96vh;min-height:600px;border:0;display:block;";
  iframe.setAttribute("allow", "clipboard-write");
  dv.container.style.padding = "0";
  dv.container.style.margin = "0";
  dv.container.appendChild(iframe);
} catch (e) {
  dv.paragraph("⚠️ 无法加载 " + path + "：" + e.message + "\n请确认文件存在，且 Dataview 已开启 *Enable JavaScript Queries*。");
}
```

---

## 双链笔记

- [[.gitignore]]
- [[# Obsidian 10 大 Skill 盘点，你用过吗？]]
- [[5个常用插件]]
- [[6a1460f0378785c31db2a5e6_能源行业AI创业产品方案-深度落地版_1.docx]]
- [[AI全链路自主决策工作流引擎实战课（上）]]
- [[ai賦能財務]]
- [[codex+obsidian]]
- [[Obsidian+Claude 视频知识点整理.docx]]
