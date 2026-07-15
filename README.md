本轮修改说明
一、US-05：论文智能问答与溯源
新增功能：
• 多轮对话：同一论文的历史问答自动拼接为 LLM 上下文
• 对话管理：新建 / 切换 / 删除对话，切换论文自动重置，删最后一对话回初始页
• 证据不足检测：LLM 输出 INSUFFICIENT_EVIDENCE 时替换为友好提示，前端显示 ⚠ 标识
• 对话持久化：JSON 存储，重启后历史可回看
• 输出格式规整：LLM 按结构化模板输出，消息文本正确换行

新增文件夹/文件：
• backend/app/services/conversation_store.py 对话持久化
• backend/app/api/routes/conversations.py 对话 CRUD 接口（3个端点）
• backend/app/services/prompt_templates.py LLM 输出格式化模板
• frontend/src/hooks/useConversations.ts 对话状态管理 Hook
• frontend/src/components/ConversationSelector.tsx 对话选择器 UI

修改文件夹/文件：
• backend/app/models/schemas.py +ConversationRecord / MessageRecord
• backend/app/api/routes/chat.py 对话管理 + 格式化注入 + 证据检查 + 消息持久化
• backend/app/api/router.py 注册 conversations 路由
• frontend/src/types.ts +Conversation / MessageRecord 类型
• frontend/src/api.ts +对话 API + conversationId 参数
• frontend/src/components/ChatPanel.tsx 集成对话选择器 + 证据警告 + 删除修复
• frontend/src/styles.css 对话选择器样式 + pre-wrap + 证据警告样式

未触及的文件夹：
• backend/app/agents/ chat_agent / coordinator 不动
• backend/app/services/runtime.py 不动
• backend/app/services/llm.py 不动
• backend/app/services/knowledge_base.py 不动
• backend/app/services/parser.py 不动
• backend/app/core/ 不动

二、US-07：图片、图表和公式问答
新增功能：
• 视觉查询自动分流：问"图X"/"表X"/"公式"→ 路由到视觉分析 Agent
• 图片/图表分析：识别类型、关键元素，标注页码
• 表格分析：解释表头含义、对比数据，不编造数值
• 公式分析：LaTeX 原文 + 逐项符号解释
• 证据不足保护：数据无关时 LLM 输出 INSUFFICIENT_EVIDENCE，前端显示 ⚠
• 无 LLM 时降级为 MinerU 原文展示

新增文件夹/文件：
• backend/app/services/visual_prompts.py 视觉关键词检测 + 4套专用 prompt + 证据规则
• backend/app/agents/visual_agent.py 视觉分析 Agent

修改文件夹/文件：
• backend/app/api/routes/chat.py 视觉查询分流 + evidence_sufficient 逻辑修复

未触及的文件夹：
• backend/app/agents/coordinator.py 不动
• backend/app/services/runtime.py 不动
• backend/app/agents/chat_agent.py 不动
• backend/app/models/schemas.py 不动
• frontend/ 全部不动
三、新增 API 端点
GET    /api/papers/{id}/conversations            列出论文下所有对话
GET    /api/papers/{id}/conversations/{cid}      获取单个对话详情
DELETE /api/papers/{id}/conversations/{cid}      删除对话
四、设计原则
所有新功能通过新建文件实现。已有核心模块（Agent 体系、路由层、调度器、
LLM 客户端、知识库、解析器、前端组件）均未被修改。chat.py 作为唯一
集成点承担分流和编排职责
