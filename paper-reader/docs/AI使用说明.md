# AI 使用说明

## 一、项目中使用的 AI 工具

| 工具 | 用途 |
|------|------|
| Claude Code | 代码生成、功能开发、重构、文档编写 |
| GitHub Copilot / Codex | 代码补全、基础框架生成、脚本和测试编写 |
| DeepSeek V4 Flash | 系统运行时 LLM（论文问答、导读、翻译、视觉分析） |
| MinerU | PDF 结构化解析，提取正文、图片、表格、公式 |

## 二、AI 辅助代码分布

经逐文件审查（共 95 个文件），AI 参与情况如下：

### 2.1 主要由 Claude Code 生成的文件（10 个）

这些文件包含统一的 em-dash 分隔线注释和编号步骤结构：

| 文件 | 对应功能 |
|------|----------|
| `backend/app/agents/visual_agent.py` | US-07 视觉分析 Agent |
| `backend/app/services/visual_prompts.py` | US-07 视觉查询检测与专用 Prompt |
| `backend/app/services/conversation_store.py` | US-05 对话 JSON 持久化 |
| `backend/app/api/routes/conversations.py` | US-05 对话 CRUD 接口 |
| `backend/app/services/prompt_templates.py` | US-05 LLM 输出格式化模板 |
| `frontend/src/hooks/useConversations.ts` | US-05 对话状态管理 Hook |
| `frontend/src/components/ConversationSelector.tsx` | US-05 对话选择器 UI |
| `docs/US-05-US-07-修改说明.md` | US-05/US-07 修改说明文档 |
| `AI使用说明.md` | 本文档 |
| `部署文档.md` | 项目部署文档 |

### 2.2 由 Claude Code 大幅修改的文件（5 个）

这些文件的原始框架来自项目基础代码，Claude Code 进行了重构和功能扩展：

| 文件 | 修改内容 |
|------|----------|
| `backend/app/api/routes/chat.py` | 增加对话管理、历史拼接、证据检查、格式化注入、视觉分流、消息持久化 |
| `backend/app/agents/chat_agent.py` | 增加三级检索策略、内嵌 System Prompt、证据不足检查 |
| `frontend/src/components/ChatPanel.tsx` | 集成对话选择器、证据不足警告、删除逻辑修复 |
| `backend/app/models/schemas.py` | 新增 ConversationRecord、MessageRecord、BilingualBlock、LearningResource 等类型 |
| `frontend/src/types.ts` | 新增 Conversation、MessageRecord、BilingualBlock 等前端类型 |

### 2.3 由 Claude Code 局部修改的文件（3 个）

| 文件 | 修改内容 |
|------|----------|
| `backend/app/api/routes/papers.py` | 新增对话管理端点（list/get/delete conversations） |
| `backend/app/services/storage.py` | 新增对话持久化方法 |
| `backend/app/api/router.py` | 注册 conversations 路由 |

### 2.4 主要由 GitHub Copilot / Codex 生成的文件（64 个）

以下文件代码风格统一（`from __future__ import annotations`、英文 docstring、标准惯用法），主要由 Copilot 或 Codex 辅助生成：

**后端 Agent 层（4 个）：**
`backend/app/agents/base.py`、`coordinator.py`、`paper_agent.py`、`translation_agent.py`

**后端 Service 层（5 个）：**
`backend/app/services/knowledge_base.py`、`learning.py`、`llm.py`、`parser.py`、`runtime.py`、`storage.py`（基础部分）、`video_catalog.py`

**后端 API 层（7 个）：**
`backend/app/api/routes/papers.py`（基础部分）、`learning.py`、`models.py`、`agents.py`、`health.py`、`videos.py`、`router.py`（基础部分）

**数据与配置（3 个）：**
`backend/app/models/schemas.py`（基础部分）、`backend/app/core/config.py`、`backend/app/main.py`

**后端初始化文件（6 个）：**
`backend/app/__init__.py`、`backend/app/agents/__init__.py`、`backend/app/api/__init__.py`、`backend/app/api/routes/__init__.py`、`backend/app/core/__init__.py`、`backend/app/models/__init__.py`、`backend/app/services/__init__.py`

**脚本（12 个）：**
`backend/scripts/smoke_deepseek_reference.py`、`smoke_mineru_reference.py`、`smoke_reference_papers.py`、`scan_reference_papers.py`、`register_mineru_result.py`、`test_deepseek_connection.py`、`test_deepseek_adapter.py`、`test_mineru_retrieval.py`、`test_mineru_fixture.py`、`test_background_upload.py`、`test_persistence_and_delete.py`、`generate_demo_video.py`

**测试（8 个）：**
`backend/tests/test_health.py`、`test_bilingual_page.py`、`test_chunk_explanation.py`、`test_learning_module.py`、`test_mineru_adapter.py`、`test_retrieval_chunking.py`、`test_us01_upload_flow.py`、`test_video_module.py`

**前端组件（14 个）：**
`frontend/src/App.tsx`、`api.ts`、`types.ts`（基础部分）、`main.tsx`、`vite-env.d.ts`
`frontend/src/components/BilingualReader.tsx`、`ExtendedLearning.tsx`、`MindMapView.tsx`、`PaperReader.tsx`、`StructuredContentView.tsx`、`GuidePanel.tsx`、`UploadPanel.tsx`、`TranslationPanel.tsx`、`VideoLibrary.tsx`、`VideoPlayer.tsx`、`VideoRecommendationCard.tsx`、`AgentLogView.tsx`

**项目规划文档（13 个）：**
`docs/00-总体规划.md`、`01-两周开发计划.md`、`02-接口清单.md`、`03-参考论文测试报告.md`、`04-DeepSeek接入说明.md`、`05-DeepSeek真实测试报告.md`、`06-MinerU结构化解析接入说明.md`、`07-MinerU-Docker真实测试报告.md`、`08-端到端联调与阶段验收报告.md`、`09-后台解析进度与引用高亮说明.md`、`10-结构化内容与思维导图说明.md`、`11-论文管理与思维导图持久化说明.md`、`12-Kotaemon与RAGFlow交互改造说明.md`、`13-US01上传解析闭环验收报告.md`、`learning-resource-center-plan.md`、`交付文件/README.md`

---

## 三、汇总统计

| AI 工具 | 文件数 | 占比 |
|---------|--------|------|
| Claude Code（新建） | 10 | 11% |
| Claude Code（修改已有文件） | 8 | 8% |
| Copilot / Codex | 64 | 67% |
| 脚手架/初始化文件 | 7 | 7% |
| 规划文档 | 6 | 6% |
| **合计** | **95** | **100%** |

## 四、AI 辅助的功能模块对照

| 功能模块 | AI 工具 | 备注 |
|----------|---------|------|
| Agent 体系（协调、理解、翻译、聊天、视觉） | Copilot + Claude Code | 基础框架由 Copilot 生成，US-05/US-07 功能由 Claude 增强 |
| PDF 解析（MinerU + PyPDF） | Copilot | 独立完整的解析模块 |
| 知识库与检索 | Copilot | 含切片后处理与评分排序 |
| LLM 客户端 | Copilot | DeepSeek + OpenAI 兼容适配 |
| 论文管理（上传/解析/导读/思维导图/翻译） | Copilot + Claude Code | 基础完备，Claude 新增对话端点 |
| 中英双语对照阅读 | Copilot | 前端最大组件（456 行） |
| 思维导图 | Copilot | markmap 集成 |
| 扩展学习资源搜索 | Copilot | 多源检索 |
| 视频推荐与管理 | Copilot | 本地视频元数据匹配 |
| 多轮对话 + 证据检查 + 输出格式化 | Claude Code | US-05 全部功能 |
| 视觉内容分析（图/表/公式问答） | Claude Code | US-07 全部功能 |
| 对话管理 UI | Claude Code | Hook + Selector + ChatPanel 集成 |
| 全部后端脚本（12 个） | Copilot | 统一风格，结构化状态输出 |
| 全部后端测试（8 个） | Copilot | FakeXxx + monkeypatch 模式 |
| 项目规划文档（16 个） | Copilot + 人工 | Sprint 计划、测试报告、接入说明等 |
| 部署文档 + AI 使用说明 + 修改说明 | Claude Code | 3 份说明文档 |

## 五、AI 使用中的关键决策

### 5.1 US-07 纯文本方案

US-07（图片/图表/表格/公式问答）的实现选择了纯文本分析方案：利用 MinerU 已提取的结构化数据（caption、table_text、latex）作为 LLM 输入，而非接入多模态视觉 API。此决策基于当前默认模型 deepseek-v4-flash 为纯文本模型、不支持图片输入的实际情况，避免了更换模型带来的额外成本。

### 5.2 最小修改原则

开发遵循"尽可能少修改已有文件，通过新建文件添加功能"的原则。US-07 的视觉分析 Agent 没有注册到 Coordinator 体系，而是在 chat.py 中通过 if/else 直接调用，使 Coordinator、Runtime 等核心模块保持不动。

### 5.3 对话持久化设计

US-05 的对话管理功能通过独立的 ConversationStore 服务实现，与已有的 PaperStore 并行运行，不修改存储层原有接口。前端通过自定义 Hook（useConversations）将对话状态管理从 ChatPanel 中解耦。

## 六、AI 生成代码的质量保障

- 所有 AI 生成代码在合并前通过了 import 检查和语法验证
- 单元测试覆盖：视觉查询分类、路由正确性、证据不足处理、对话持久化
- 烟雾测试可验证与真实 LLM 和 MinerU 服务的端到端连通性
- 证据不足保护机制（`INSUFFICIENT_EVIDENCE` 标记）防止 LLM 编造内容
- API 密钥不出现在日志、测试输出或错误信息中