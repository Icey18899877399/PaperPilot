# MinerU结构化解析接入说明

## 本阶段完成内容

系统已按MinerU当前FastAPI接口接入同步解析端点`POST /file_parse`。上传字段使用`files`，并开启公式、表格、图片与内容列表输出。后端请求ZIP响应，将文件安全解压至`backend/data/assets/<paper_id>`，读取`content_list.json`并转换为统一的`PaperChunk`。

结构化字段包括：内容类型、页码、归一化坐标`bbox`、图片资源地址、图片标题与脚注、表格HTML与可检索文本、公式LaTeX。聊天Agent检索时会识别“图片、图表、表格、公式”等问题意图，优先召回相应内容，并在引用中返回页码、类型、坐标和图片地址。前端可以点击引用定位PDF原页，也会直接展示MinerU抽取的图片或表格截图。

## 本机部署方式

本项目后端使用8000端口，因此MinerU使用8001端口。当前电脑已经完成Docker部署，Docker数据盘位于`D:\DockerDesktopData`，MinerU目录位于`D:\软件工程_小学期\mineru-docker`。

```powershell
cd D:\软件工程_小学期\mineru-docker
# 首次部署或需要重新安装时
powershell -ExecutionPolicy Bypass -File setup.ps1
# 日常启动
docker compose up -d
```

安装完成后，在项目`.env`中加入：

```dotenv
MINERU_API_URL=http://127.0.0.1:8001
MINERU_BACKEND=pipeline
MINERU_LANGUAGE=ch
MINERU_TIMEOUT_SECONDS=3600
```

验证服务：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
```

随后正常启动论文阅读系统并重新上传测试论文。上传后可通过以下接口核对解析结果：

```text
GET /api/papers/{paper_id}/contents
GET /api/papers/{paper_id}/contents?kind=image
GET /api/papers/{paper_id}/contents?kind=table
GET /api/papers/{paper_id}/contents?kind=equation
```

## 验证标准

1. 上传包含图片、表格和公式的PDF后，论文状态为`ready`。
2. 内容接口的`counts`至少出现实际存在的`image`、`table`、`equation`类型。
3. 图片或表格条目的`resource_url`可在浏览器访问，`bbox`包含四个坐标值。
4. 表格条目保留`table_html`与转换后的`table_text`，公式条目保留`latex`。
5. 提问“解释第X页公式”“表格中哪项最好”“图1表达什么”时，聊天引用优先返回相应类型，并能点击定位原页。

## 性能说明

当前电脑没有NVIDIA GPU，采用MinerU 3.4.0的`pipeline`纯CPU方案。Docker配置把处理窗口设为4、并发请求设为1，以降低约32GB内存机器上的峰值占用。镜像已补装`six`并锁定`pdftext==0.6.3`以兼容当前pipeline实现。22页真实论文解析耗时约361秒，结果见`07-MinerU-Docker真实测试报告.md`。
