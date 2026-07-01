# TALOS Dashboard 部署说明

更新时间：2026-06-26 15:08

满屏首页调整：2026-06-26 15:15

## 部署范围

- 源码目录：`D:\亿云能源科技售电交易数据库\talos-dashboard`
- Obsidian 库目录：`D:\亿云能源科技售电交易数据库`
- 已部署到库根目录：
  - `dashboard.html`
  - `homepage.md`
  - `refresh-dashboard.py`
- 已部署 CSS 片段：
  - `.obsidian\snippets\talos-dashboard-home.css`

## 已确认配置

- 已启用社区插件：
  - `dataview`
  - `homepage`
- Dataview 已开启 JavaScript 查询。
- Homepage 已设置 `homepage.md` 为启动首页。
- 外观 CSS 片段已启用 `talos-dashboard-home`。
- 首页包装笔记已设置 `dashboard.html` 为内容源，并把 iframe 改为满宽满高。
- CSS 片段已隐藏首页笔记页眉和页面外壳，让仪表盘铺满当前 Obsidian 页面。

## 数据刷新

手动刷新命令：

```powershell
$env:PYTHONIOENCODING='utf-8'
python 'D:\亿云能源科技售电交易数据库\refresh-dashboard.py' --vault 'D:\亿云能源科技售电交易数据库'
```

最近一次刷新结果：

- 知识笔记：17
- 收件箱：0
- 待审批：0
- 偏好候选：0
- 分布：Projects 11、Materials 2、Insights 2、Archive 2、Journal 0、Inbox 0

## 备份与恢复

部署前备份目录：

`D:\亿云能源科技售电交易数据库\talos-dashboard-backup-20260626-150811`

如需恢复旧版本，把备份目录里的同名文件复制回库根目录；CSS 片段复制回 `.obsidian\snippets\`。

## 使用方式

完全退出 Obsidian 后重新打开，应自动进入 `homepage.md` 对应的 TALOS Dashboard。若没有自动打开，可在 Obsidian 命令面板中运行 `Homepage: Open homepage`。

如果页面没有立刻铺满，进入 Obsidian `设置 -> 外观 -> CSS 片段`，关闭再打开 `talos-dashboard-home`，然后重新打开首页。
