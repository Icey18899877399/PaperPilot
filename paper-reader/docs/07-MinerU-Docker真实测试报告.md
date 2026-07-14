# MinerU Docker真实测试报告

## 部署结果

MinerU已采用Docker方式部署在D盘。Docker Desktop数据盘由C盘迁移至`D:\DockerDesktopData\wsl`，MinerU部署目录为`D:\软件工程_小学期\mineru-docker`，模型和配置位于`home`，解析结果位于`output`。原有`zhiyuan-postgres`容器及数据库卷在迁移后正常恢复。

镜像为`paper-reader-mineru:3.4.0-cpu`，只安装pipeline后端。服务容器为`paper-reader-mineru`，宿主机地址为`http://127.0.0.1:8001`。健康检查结果：MinerU 3.4.0、protocol 2、最大并发1、处理窗口4。

镜像逻辑大小约3.03GiB，pipeline模型目录约2.5GiB。测试完成后C盘剩余约5.7GB、D盘剩余约349.2GB，MinerU与原`zhiyuan-postgres`容器均处于healthy状态。

## 兼容问题与修复

首次真实调用发现系统代理截获本机请求并返回502，已在论文阅读系统的MinerU `httpx`客户端中设置`trust_env=False`，保证`127.0.0.1`请求不经过系统代理。

MinerU 3.4.0的pipeline运行时还存在两个依赖声明问题：缺少`six`会导致`No module named 'six'`；自动安装的`pdftext 0.7.1`返回不可直接迭代的`PageChars`，与MinerU当前实现不兼容。Docker镜像现已安装`six 1.17.0`并锁定`pdftext 0.6.3`，两项错误均已消除。

## 真实论文测试

测试文件：`2025.coling-main.353.pdf`，共22页。CPU pipeline完整解析耗时360.92秒，生成196个结构块：正文170、图片2、表格13、图表6、列表3、公式2；其中20个块带有可访问的图片或表格资源。

结构化资源已保存至：

```text
D:\软件工程_小学期\paper-reader\backend\data\assets\mineru-smoke-2025.coling-main.353
```

论文阅读系统`.env`已配置`MINERU_API_URL=http://127.0.0.1:8001`和`MINERU_BACKEND=pipeline`。后续从系统页面上传PDF时，将自动使用MinerU而非PyPDF回退解析，并把图片、表格、图表和公式加入知识库及聊天引用。
