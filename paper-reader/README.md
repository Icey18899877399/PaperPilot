# 多Agent论文智能阅读系统

面向课程小学期的两周制项目骨架。系统支持论文 PDF 上传、解析、智能导读、中英翻译、按页生成并缓存中英双页对照、基于论文内容的问答、原文引用定位，以及聊天中的本地学习视频推荐与播放。

## 技术范围

- 前端：React、TypeScript、Vite、PDF.js（通过 react-pdf）
- 后端：FastAPI、Python
- 文档解析：MinerU 适配器；未配置时使用 PyPDF 开发回退
- Agent：协调 Agent、论文理解 Agent、翻译 Agent、聊天问答 Agent
- 检索：可替换知识库接口；骨架默认提供轻量内存检索
- 视频：本地 MP4 元数据匹配和网页播放，不分析视频内容

## 目录

- `backend/`：API、Agent、解析、知识库和视频资源服务
- `frontend/`：论文阅读、导读、聊天、翻译和视频播放界面
- `docs/`：架构、接口、两周计划及课程交付文件目录
- `scripts/`：Windows 开发启动脚本

## 快速启动

1. 复制 `.env.example` 为 `.env`。
2. 后端：

   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   uvicorn app.main:app --reload
   ```

3. 前端：

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

4. 打开 `http://localhost:5173`，后端接口文档位于 `http://localhost:8000/docs`。

## 当前骨架与后续实现

当前代码已经使用课程参考论文跑通核心闭环，并支持论文元数据与切片索引持久化。接入真实模型、MinerU服务和向量数据库后，可逐步替换开发回退实现，不需要改变前端主要接口。

## 参考论文烟雾测试

```powershell
cd backend
python scripts\scan_reference_papers.py "D:\软件工程_小学期\reference"
python scripts\smoke_reference_papers.py "D:\软件工程_小学期\reference"
```

烟雾测试使用隔离的临时数据目录，不会污染正式上传目录。它会验证健康检查、PDF上传、文本解析、智能导读、RAG检索、页码引用、Agent日志和索引持久化。

## 配置DeepSeek

不要把API Key发到聊天、截图或提交到Git。请在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\configure-deepseek.ps1
```

脚本会隐藏密钥输入并将配置写入已被Git忽略的 `.env`。随后执行：

```powershell
cd backend
python scripts\test_deepseek_connection.py
python scripts\smoke_deepseek_reference.py "D:\软件工程_小学期\reference\2025.coling-main.353.pdf"
```

默认使用 `deepseek-v4-flash` 且关闭思考模式，适合低成本功能联调。接口 `GET /api/models/status` 只返回模型配置状态，不返回API密钥。

当前已使用 `2025.coling-main.353.pdf` 完成真实联网测试，论文导读、3个阅读重点、带4条页码引用的问答及英译中均通过。测试记录见 `docs/05-DeepSeek真实测试报告.md`。

## 接入MinerU结构化解析

代码已支持MinerU当前`/file_parse` ZIP接口，可保存并索引正文、图片、图表、表格和公式。图片路径、页码、页内坐标、表格HTML和公式LaTeX会进入内容接口与聊天引用。

```powershell
# 首次安装与模型下载（本机已经完成）
cd D:\软件工程_小学期\mineru-docker
powershell -ExecutionPolicy Bypass -File setup.ps1

# 日常启动
docker compose up -d
```

当前Docker数据、MinerU镜像和模型均位于D盘，服务使用8001端口，项目`.env`已设置`MINERU_API_URL=http://127.0.0.1:8001`。完整配置和验收标准见`docs/06-MinerU结构化解析接入说明.md`，真实测试结果见`docs/07-MinerU-Docker真实测试报告.md`。

如果已经通过`smoke_mineru_reference.py`完成真实解析，可直接把结果注册到论文库，避免重复解析同一篇论文：

```powershell
cd backend
python scripts\register_mineru_result.py "D:\软件工程_小学期\reference\2025.coling-main.353.pdf"
```

脚本会复用`data/assets/mineru-smoke-<文件名>`中的结构化结果，保存论文记录和检索切片；重启后端后即可在前端论文库中阅读、生成导读并进行图表/表格/公式问答。

需要验证聊天中的本地视频推荐与网页内播放时，可生成随项目保存的演示MP4：

```powershell
cd backend
python scripts\generate_demo_video.py
```
