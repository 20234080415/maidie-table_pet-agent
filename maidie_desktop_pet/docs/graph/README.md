# Graphify 项目图谱

本目录中的三个主要文件由 `graphifyy 0.9.5` 对当前仓库运行真实 Graphify AST
提取、聚类和导出流程生成：

- [`graph.html`](graph.html)：可在浏览器中打开的交互式图谱。
- [`graph.json`](graph.json)：Graphify/GraphRAG 可读取的节点、关系与社区数据。
- [`GRAPH_REPORT.md`](GRAPH_REPORT.md)：Graphify 生成的语料统计、社区、God Nodes、
  连接与建议问题报告。

## 本次扫描范围

Graphify 检测到 218 个受支持文件：178 个代码文件、19 个文档和 21 张图片。
当前环境没有可供 Graphify 语义提取使用的 API Key，因此本次正式产物只包含对 178
个代码文件的确定性 AST 提取，不包含文档和图片的语义节点或关系。最终图谱包含
1834 个节点、4205 条构建后边和 93 个社区；LLM token 成本为 0。

这与上一版手工图谱不同：当前 `graph.json`、`graph.html` 和 `GRAPH_REPORT.md` 均为
Graphify 库实际生成的输出，没有保留或伪装手写节点。

## 图谱健康信息

Graphify 对原始提取结果的只读诊断报告了：494 条悬空端点边、1 条自环、86 条完全
重复边，以及无向构建下 256 条同端点折叠边。Graphify 在构建最终图谱时将 4955 条
原始边归并为 4205 条边。图谱仍可浏览和查询，但关系数量不应被解释为无损调用图。

## 重新生成

Graphify 安装在 `maidie` conda 环境中：

```powershell
conda run -n maidie python -m pip install graphifyy
conda run -n maidie graphify install --platform codex
conda run -n maidie graphify .
```

在有受支持语义后端 Key 的环境中，`graphify .` 可处理代码以外的文档和图片。没有
Key 时，该 CLI 会在语义阶段停止；代码结构仍可依照已安装 Graphify Skill 的 AST
流程生成。默认 CLI 输出位于 `graphify-out/`，确认后将 `graph.json`、`graph.html`
和 `GRAPH_REPORT.md` 复制到本目录。

不要手工编辑生成的三个主产物；需要补充范围、限制或复现信息时更新本说明文件。
