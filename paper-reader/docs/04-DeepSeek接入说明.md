# DeepSeek接入说明

## 1. 采用方案

系统继续使用已有OpenAI兼容LLM边界，并增加DeepSeek专用环境变量。DeepSeek配置优先于通用的 `LLM_*` 配置，因此后续切换其他模型时不需要修改Agent代码。

默认配置：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_THINKING=false
```

DeepSeek官方文档说明其API兼容OpenAI Chat Completions格式。项目调用 `POST /chat/completions`，使用Bearer鉴权；测试阶段选择V4 Flash并关闭思考模式，以缩短响应时间和降低联调消耗。

旧名称 `deepseek-chat` 和 `deepseek-reasoner` 将在2026年7月24日停用，因此项目不再将其作为默认值。若检测到旧名称，模型状态接口会返回迁移提示。

## 2. 安全配置

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\configure-deepseek.ps1
```

脚本使用隐藏输入读取API Key，并写入根目录的 `.env`。该文件已加入 `.gitignore`，不得复制到PPT、测试报告、AI对话截图或Git仓库中。

如果粘贴后脚本提示API Key过短，说明终端只接收到部分内容。请重新运行脚本，用 `Ctrl+V` 或右键粘贴完整Key；脚本只显示长度检查结果，不显示Key内容。

也可以手动复制 `.env.example` 为 `.env`，但必须确保：

1. 等号两侧不要添加多余引号；
2. BASE_URL不要写成控制台网页地址；
3. 不要在BASE_URL后重复添加 `/chat/completions`；
4. 修改配置后重启FastAPI服务。
5. DeepSeek API Key通常不是单个字符；项目会拒绝长度小于20的配置。

## 3. 验证顺序

### 3.1 离线适配测试

```powershell
cd backend
python scripts\test_deepseek_adapter.py
```

该测试使用Mock响应，不发起网络请求、不产生费用，验证请求地址、Bearer鉴权、V4模型名、思考模式开关和JSON输出解析。

### 3.2 最小联网测试

```powershell
python scripts\test_deepseek_connection.py
```

成功时只输出模型名称、延迟和响应长度，不显示API Key。

### 3.3 参考论文真实测试

```powershell
python scripts\smoke_deepseek_reference.py "D:\软件工程_小学期\reference\2025.coling-main.353.pdf"
```

该测试会使用临时数据目录，依次验证：

- PDF上传和解析；
- DeepSeek结构化论文导读；
- 基于论文切片的中文问答；
- 原文页码引用；
- 英译中翻译Agent。

脚本会产生三次模型调用，只输出统计信息，不打印完整论文回答。

## 4. 相关接口

### GET /api/models/status

返回模型提供方、是否配置、BASE_URL、模型名称、思考模式和旧模型警告。不会返回API Key。

### POST /api/models/test

发送最小提示词验证模型连接。未配置时返回409；网络、密钥、余额或模型错误以脱敏后的502信息返回。

## 5. 当前实现效果

- 论文理解Agent要求DeepSeek返回JSON对象，并拆分为概述、3个阅读重点和3个阅读问题；
- 聊天Agent只把检索到的论文片段交给DeepSeek，并在响应中保留独立引用数组；
- 翻译Agent要求保留术语、公式和引用编号；
- 所有Agent共用同一LLM适配器和错误处理机制；
- 前端顶部展示“模型未配置”或当前DeepSeek模型名称。
