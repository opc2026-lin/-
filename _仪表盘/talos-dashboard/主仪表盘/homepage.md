---
title: 亿云电力交易首页
date: 2026-06-29
tags: [仪表盘, 首页, 电力交易]
status: active
type: system
summary: "Obsidian 启动首页：用 Dataview JS 内联亿云电力交易控制台，整页铺满、卡片点击经 postMessage 在库内直达笔记。"
cssclasses: [dashboard-home]
---

```dataviewjs
// === 导航桥：iframe 内卡片点击 → 在 Obsidian 内打开对应笔记/文件 ===
if (!window.__talosNavInstalled) {
  window.__talosNavInstalled = true;
  window.addEventListener("message", async (ev) => {
    const d = ev.data;
    if (!d || d.type !== "yiyun-open" || !d.path) return;
    const p = d.path;
    const scriptDir = "_负荷预测存档/调试脚本";
    const launcherMap = [
      [/\/训练预测_v.*\.bat$/i, `${scriptDir}/train_forecast.lnk`],
      [/\/回测_v.*\.bat$/i, `${scriptDir}/backtest_forecast.lnk`],
      [/\/校验_v.*\.bat$/i, `${scriptDir}/verify_forecast.lnk`]
    ];
    const redirected = launcherMap.find(([re]) => re.test(p))?.[1] || p;
    try {
      if (redirected.endsWith("/")) {
        const folderPath = redirected.replace(/\/$/, "");
        const folder = app.vault.getAbstractFileByPath(folderPath);
        if (folder) {
          const explorer = app.internalPlugins?.getPluginById?.("file-explorer");
          if (explorer?.instance?.revealInFolder) {
            try { explorer.instance.revealInFolder(folder); } catch(e) {}
          }
          const leaves = app.workspace.getLeavesOfType("file-explorer");
          if (leaves.length) {
            app.workspace.revealLeaf(leaves[0]);
            try { leaves[0].view.expandFolder?.(folder); } catch(e2) {}
          }
        }
      } else {
        if (/\.cmd$/i.test(redirected) || /\.bat$/i.test(redirected)) {
          const file = app.vault.getAbstractFileByPath(redirected);
          if (file && app.openWithDefaultApp) { app.openWithDefaultApp(file); return; }
        }
        if (/\.(pdf|xlsx|csv|html?)$/i.test(redirected)) {
          const file = app.vault.getAbstractFileByPath(redirected);
          if (file && app.openWithDefaultApp) { app.openWithDefaultApp(file); return; }
        }
        await app.workspace.openLinkText(redirected, "", "tab");
      }
    } catch (err) {
      console.error("talos-open 失败:", redirected, err);
      const file = app.vault.getAbstractFileByPath(redirected);
      if (file) {
        try { app.openWithDefaultApp(file); } catch(e2) {}
      }
    }
  });
}

// === 实时读取仪表盘 HTML 并注入 iframe ===
const path = "dashboard.html";
try {
  const inject = JSON.stringify({
    train: "_负荷预测存档/调试脚本/train_forecast.lnk",
    verify: "_负荷预测存档/调试脚本/verify_forecast.lnk",
    backtest: "_负荷预测存档/调试脚本/backtest_forecast.lnk"
  });
  const html = await app.vault.adapter.read(path);
  const htmlWithData = html.replace("</body>", `<script>window.__BAT_SCRIPTS__ = ${inject};</script></body>`);
  const iframe = document.createElement("iframe");
  iframe.srcdoc = htmlWithData;
  iframe.style.cssText = "width:100%;height:100%;min-height:100vh;border:0;display:block;";
  iframe.setAttribute("allow", "clipboard-write");
  dv.container.style.padding = "0";
  dv.container.style.margin = "0";
  dv.container.appendChild(iframe);
} catch (e) {
  dv.paragraph("⚠️ 无法加载 " + path + "：" + e.message + "\n请确认文件存在，且 Dataview 已开启 *Enable JavaScript Queries*。");
}
```

