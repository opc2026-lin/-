---
tags: [AI, AI Agent, AI Skill, 开源]
---
#

这段视频介绍了一款刚开源的AI工具项目PilotDeck，它由清华大学THUNLP实验室、面壁智能OpenBMB与AI9stars联合研发，可让一个人指挥一支智能体军队，适用于通用多任务场景，有以下亮点：
&#x20;
\- 独立工作空间（WorkSpace）：每个项目的文件、记忆、技能完全隔离，避免交叉污染。
\- 白盒记忆：记忆全程可追溯、可编辑、可回滚，且有Dream Mode自动整理记忆。
\- 智能路由：自动匹配模型，复杂任务用强模型，简单任务降级使用，实测可节省70%成本。
\- 后台持续执行（Always-on）：能主动发现任务并生成文件，离开键盘也可继续工作，还能避免智能体（Agent）互相干扰导致成本失控。

PilotDeck 完整说明：是什么、装在哪、怎么用

一、它到底是什么？

PilotDeck 是「AI智能体操作系统（Agent OS）」，不是单一的APP，也不是单个Skill，而是一个完整的本地运行时平台，相当于给你的电脑装了一套能管理、调度、指挥多个AI智能体干活的"操作系统"。

它的核心定位&#x662F;**"一个人指挥一支智能体军队"的生产力工具**，由清华大学THUNLP实验室、面壁智能OpenBMB与AI9stars联合研发，2026年5月28日正式开源（AGPL-3.0协议，完全免费可商用）。

二、它有哪些形态？装在哪里？

它提供4种部署方式，覆盖不同用户需求：

1. 桌面端APP（最推荐普通人用）

* 支持：macOS（Apple Silicon）、Windows（x64/ARM64）
* 下载：直接从官网 [https://pilotdeck.openbmb.cn/](https://pilotdeck.openbmb.cn/) 下载安装包，双击安装即可，不用敲命令

2. 一键脚本安装（macOS/Linux）

* 打开终端执行： curl -fsSL [https://raw.githubusercontent.com/OpenBMB/PilotDeck/main/install.sh](https://raw.githubusercontent.com/OpenBMB/PilotDeck/main/install.sh) | bash 
* 安装完成后运行  pilotdeck  启动服务，浏览器访问  [http://localhost:3001](http://localhost:3001)  进入Web操作界面

3. Docker Compose 部署

* 适合服务器或有Docker基础的用户，一键启动完整服务，数据持久化更方便

4. 源码编译

* 适合开发者二次开发，从GitHub仓库 [https://github.com/OpenBMB/PilotDeck](https://github.com/OpenBMB/PilotDeck) 拉取源码编译

⚠️ 重要：PilotDeck本身不自带大模型，它是一个调度平台，需要你自己配置各大模型的API Key（DeepSeek、OpenAI、通义千问等），它会根据任务复杂度自动调用合适的模型。

三、5步快速上手使用

1. 安装并启动

* 桌面端：安装后直接打开APP，自动启动本地服务
* 脚本安装：运行  pilotdeck  命令，浏览器打开  [http://localhost:3001](http://localhost:3001) 

2. 配置模型API

* 编辑配置文件  \~/.pilotdeck/pilotdeck.yaml ，填入你的模型API Key和端点
* 示例（DeepSeek）：

yaml

schemaVersion: 1

agent:

model: deepseek/deepseek-v4-pro

model:

providers:

deepseek:

protocol: openai

url: [https://api.deepseek.com/v1](https://api.deepseek.com/v1)apiKey: sk-你的APIKey

 

* 支持同时配置多个模型，智能路由会自动选择最优的

3. 创建独立WorkSpace（工作舱）

* 点击"新建工作舱"，给项目命名（比如"公众号写作"、"爬虫项目"）
* 每个工作舱有独立的文件系统、记忆存储、技能集，多项目并行不会互相干扰

4. 装配所需技能（Skill）

* 进入工作舱右上角的"Skills"入口，从官方商店一键安装需要的技能（比如PDF解析、代码生成、浏览器控制）
* 也支持上传本地自定义Skill文件夹，扩展能力

5. 下达任务，让AI干活

* 在工作舱的聊天框用自然语言描述任务（比如"帮我整理这10篇论文的摘要，生成一份行业报告"）
* 开启"Always-on"模式，AI会在后台持续执行，主动发现任务、生成文件，你离开键盘也能继续工作
* 随时查看执行日志、记忆链路，出错了可以手动编辑记忆或回滚状态

四、核心能力回顾（对应视频介绍）

* ✅ 独立工作舱：每个项目文件、记忆、技能完全隔离，无交叉污染
* ✅ 白盒记忆：全程可追溯、可编辑、可回滚，Dream Mode自动整理记忆
* ✅ 智能路由：复杂任务用强模型，简单任务用轻量模型，实测省70% Token成本
* ✅ 后台常驻执行：主动推进任务，不用你守着等回复

以下是 支持接入PilotDeck、免费可用的大厂大模型清单，均提供公开API，适配平台的模型配置要求，按“厂商+模型+核心能力”整理，方便直接选用：

一、国内大厂免费大模型（无墙、访问稳定）

1. 字节跳动 - 豆包系列

* 模型：豆包4.0（免费版）、豆包3.5 Turbo（免费版）
* 核心能力：通用任务（文档处理、文案生成）、代码辅助、逻辑推理，支持长文本处理
* API接入：通过“火山方舟”平台申请API Key（免费额度充足，日常使用足够）

2. 阿里 - 通义千问系列

* 模型：通义千问3.5（免费版）、通义千问2.0（免费版）
* 核心能力：中文语境适配强、办公自动化（表格/PPT处理）、轻量代码生成
* API接入：登录“通义千问开放平台”申请，免费额度支持百万级Token调用

3. 百度 - 文心一言系列

* 模型：文心一言4.0（免费体验版）、文心一言3.5（免费版）
* 核心能力：多模态处理（文本+图片）、企业级办公任务、批量数据整理
* API接入：通过“百度智能云千帆大模型平台”申请，免费额度可满足日常调度

4. 华为 - 盘古大模型

* 模型：盘古大模型3.0（免费版）、盘古Lite（轻量免费版）
* 核心能力：技术文档处理、代码调试、工业/办公场景适配
* API接入：登录“华为云ModelArts”平台申请，免费额度无时间限制

5. 智谱AI - 智谱清言系列

* 模型：智谱清言3.5（免费版）、智谱GLM-4（免费体验版）
* 核心能力：代码生成（接近Codex体验）、数学计算、复杂逻辑拆解
* API接入：通过“智谱AI开放平台”申请，免费版支持高频调用

二、国际大厂免费大模型（需科学上网）

1. Google - Gemini系列

* 模型：Gemini 1.5 Flash（免费版）、Gemini 1.0 Pro（免费版）
* 核心能力：长文本处理（支持100万Token）、代码生成（多语言）、跨模态任务
* API接入：通过“Google AI Studio”申请API Key，免费额度每月可用，支持商用

2. Meta - Llama 3

* 模型：Llama 3 8B（免费开源版）、Llama 3 70B（免费API版）
* 核心能力：通用任务、代码辅助、创意生成，适配英文场景
* API接入：通过“Meta AI Platform”或第三方代理平台（如Together.ai）申请免费API

3. Anthropic - Claude 3 Haiku

* 模型：Claude 3 Haiku（免费体验版）
* 核心能力：安全合规性强、长文档解析、办公自动化（邮件/报表处理）
* API接入：登录“Anthropic Console”申请，免费额度支持日常轻量使用

三、接入关键说明（适配PilotDeck）

1. 所有模型均支持 OpenAI兼容协议，配置时只需在PilotDeck的  pilotdeck.yaml  中填写模型的API URL、API Key，选择“openai”协议即可（示例如下）：

yaml

model:

providers:

doubao:  # 自定义名称

protocol: openai

url: [https://aquasearch.ai/v1](https://aquasearch.ai/v1)  # 豆包API端点（需从官方获取）

apiKey: sk-你的豆包APIKey

 

2. 免费版模型有 Token额度限制（大厂通常提供“永久免费基础额度+定期赠送额外额度”），日常办公、代码辅助、任务调度完全够用，超量后按需付费即可。

3. 若需要“像Codex一样专注代码工作”，优先选 智谱清言3.5、Gemini 1.5 Flash、Llama 3 70B，它们的代码生成/调试能力更突出，适配PilotDeck的“技能插件”（如代码编译、自动部署）。

需要我帮你整理某款模型（比如豆包/ Gemini）的 详细API配置步骤+PilotDeck适配代码 吗？

*

---

## 双链笔记

- [[Hermes skill]]
- [[# OpenClaw, Hermes, Codex 横向评测]]
- [[# 斯坦福的课程太夯了！CSE146S 全解析]]
- [[7.5万，AI知识库开发]]
- [[Agent时代，项目管理别再只看Issue了]]
