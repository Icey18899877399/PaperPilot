# DeepSeek真实联网测试报告

## 1. 测试目的

验证多Agent论文智能阅读系统能否通过DeepSeek官方API完成模型连接、论文结构化导读、基于论文内容的聊天问答、原文页码引用和学术翻译。

## 2. 测试环境

- 测试日期：2026年7月13日
- 模型提供方：DeepSeek
- 模型：`deepseek-v4-flash`
- 思考模式：关闭
- API地址：`https://api.deepseek.com`
- PDF解析：PyPDF开发回退
- 测试论文：`2025.coling-main.353.pdf`
- 论文页数：22页

API Key仅保存在项目根目录的 `.env` 中，测试脚本不输出密钥或完整模型回答。

## 3. 连接测试

执行命令：

```powershell
python scripts\test_deepseek_connection.py
```

测试结果：

```text
DEEPSEEK_CONNECTION_OK provider=deepseek model=deepseek-v4-flash latency_ms=2117 response_length=2
```

结论：DeepSeek API鉴权、模型名称、BASE_URL和Chat Completions接口均配置正确。

## 4. 参考论文端到端测试

执行命令：

```powershell
python scripts\smoke_deepseek_reference.py "D:\软件工程_小学期\reference\2025.coling-main.353.pdf"
```

测试结果：

| 检查项 | 结果 |
|---|---:|
| PDF页数 | 22页 |
| 智能导读概述长度 | 130字符 |
| 阅读重点数量 | 3个 |
| 论文问答长度 | 680字符 |
| 原文引用数量 | 4条 |
| 翻译结果长度 | 22字符 |
| 全流程耗时 | 12.28秒 |

完整测试状态：

```text
DEEPSEEK_REFERENCE_SMOKE_OK
```

## 5. 验证结论

本轮测试证明以下模块已经形成真实闭环：

1. 论文上传和PyPDF文本解析；
2. 论文切片和知识库检索；
3. 协调Agent调用论文理解Agent；
4. DeepSeek生成结构化中文导读；
5. 聊天Agent基于检索片段回答论文问题；
6. 回答返回4条独立的原文页码引用；
7. 翻译Agent完成英文到中文的学术翻译；
8. Agent运行过程生成可查询日志。

## 6. 当前边界与下一阶段

- 当前引用来源是PyPDF文字切片，图片、表格和公式尚未接入MinerU结构化输出；
- 本次脚本仅验证结果字段和长度，后续应增加人工质量评价表；
- 前端已经显示DeepSeek配置状态，但仍需补充完整的中英文对照交互；
- 下一阶段应接入MinerU，优先选择图表和公式较多的论文进行多模态解析测试。

