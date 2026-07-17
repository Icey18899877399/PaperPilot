# 阅读工作台PDF页面空白修复说明

修复日期：2026-07-15。基于 main 分支 `30af149`（Merge integrated PaperPilot features）之后的本地修改，供合并时参考。

## 问题现象

「阅读工作台」中间栏的在线阅读区，每一页 PDF 渲染后下方都会多出约一整页高度的空白，滚动体验异常。「中英对照」页的 PDF 无此问题。

## 根因

`PaperReader.tsx` 的 `<Page>` 开启了 `renderAnnotationLayer`（链接注释层），但入口文件只导入了 `TextLayer.css`，没有导入 react-pdf 配套的 `AnnotationLayer.css`。缺少该样式时注释层不是 `position: absolute` 的覆盖层，而是按文档流排在页面画布下方——它与画布等高，因此每页高度恰好翻倍，多出的那段"空白"实际是透明的链接注释元素。

实测（22 页 COLING 测试论文第 1 页）：画布 861px，`.react-pdf__Page` 总高 1722px（= 2 × 861），`.annotationLayer` 为 `position: static`、含 36 个注释元素。

旁证：`BilingualReader.tsx` 用 `renderAnnotationLayer={false}` 绕开了同一问题，所以对照页正常。

## 修改内容（共 1 个文件、1 行新增）

**`frontend/src/main.tsx`**：新增一行样式导入（第 4 行）：

```diff
 import "react-pdf/dist/Page/TextLayer.css";
+import "react-pdf/dist/Page/AnnotationLayer.css";
```

react-pdf 9.2.1 的 package.json exports 会把该路径映射到 `dist/esm/Page/AnnotationLayer.css`，与现有 TextLayer.css 导入方式一致。

## 实现效果

1. 每页 PDF 下方的整页空白消失，`.react-pdf__Page` 高度与画布相等（修复后实测两者同为 1018px，注释层变为 `position: absolute` 覆盖层）。
2. 论文内的引用跳转、脚注与外部链接保持可点击（未采用关闭注释层的绕行方案，功能无损失）。
3. 控制台不再出现 `Warning: AnnotationLayer styles not found` 警告。

## 合并注意事项

- 改动只有 `main.tsx` 一行新增，与其他分支冲突概率极低；若冲突，保证 `AnnotationLayer.css` 的导入存在即可。
- 该 CSS 仅作用于渲染了注释层的组件；`BilingualReader` 已关闭注释层，不受影响。
- 可选后续（本次未改动）：根因修复后，`BilingualReader.tsx:389` 的 `renderAnnotationLayer={false}` 理论上可以改回 `renderAnnotationLayer` 让对照页链接恢复可点，建议先与原作者确认当初关闭是否另有原因。
