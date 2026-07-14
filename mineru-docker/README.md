# MinerU 3.4 CPU Docker部署

该目录用于论文阅读系统的MinerU结构化解析服务。镜像、模型和输出均落在D盘：Docker Desktop数据盘位于`D:\DockerDesktopData`，模型与`mineru.json`位于本目录`home`，解析输出位于`output`。

服务地址：`http://127.0.0.1:8001`。项目后端通过`MINERU_API_URL=http://127.0.0.1:8001`调用。

```powershell
cd D:\软件工程_小学期\mineru-docker
powershell -ExecutionPolicy Bypass -File setup.ps1
```

常用命令：

```powershell
docker compose ps
docker compose logs -f --tail 100
docker compose restart
docker compose down
```

本机没有NVIDIA GPU，因此只安装`mineru[pipeline]==3.4.0`并下载pipeline模型，不包含vLLM/VLM模型。公式和表格解析默认开启，并发限制为1以控制内存峰值。

为兼容MinerU 3.4.0的pipeline运行时，镜像额外安装`six==1.17.0`，并把`pdftext`锁定为`0.6.3`，避免新版`PageChars`接口导致解析失败。

已使用`2025.coling-main.353.pdf`完成22页真实测试：共得到196个结构块，包括2个图片、13个表格、6个图表和2个公式，CPU解析耗时约361秒。
