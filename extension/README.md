# Ontology Platform Browser Extension

通用 Chrome 扩展，作为 **Browser Action Adapter** 的执行端：平台下发 `BrowserCommand`，扩展在当前浏览器会话中执行 DOM 操作并回传 `PageState` / 采集记录。

## 架构

```
Admin / Agent API  →  BrowserActionManager  →  SQLite browser_runs
                              ↑
                    Chrome Extension (poll + execute)
                              ↓
                     CaptureBatch → Connector ingest → Ontology
```

- **平台侧**：Connector YAML 定义 `browser_script` / `browser_actions`（scripted 模式）或 `capture_instructions`（agent_loop 占位）。
- **扩展侧**：不内置业务逻辑，只实现命令协议（click / fill / extract / snapshot …）。

## 安装

1. Chrome 打开 `chrome://extensions`
2. 开启「开发者模式」
3. 「加载已解压的扩展程序」→ 选择本目录 `extension/`
4. 扩展选项中设置 **平台 Admin 地址**（默认 `http://127.0.0.1:8765`）

## 使用

1. 在 Admin **数据连接** 中创建 `mode: browser_extension` 的连接器（或调用 API）。
2. 点击 **Extension 采集**，或通过 API 创建 run：
   ```bash
   curl -X POST http://127.0.0.1:8765/api/connectors/browser_demo/browser-run \
     -H 'Content-Type: application/json' \
     -d '{"auto_sync": false}'
   ```
3. 扩展每 5 秒轮询 `GET /api/browser/runs/pending`，自动拾取任务并在标签页执行。
4. 打开 Side Panel 查看当前任务状态。

## 协议

| 端点 | 说明 |
|------|------|
| `POST /api/browser/runs` | 创建任务 |
| `GET /api/browser/runs/pending` | 扩展轮询待执行 |
| `POST /api/browser/runs/{id}/step` | 上报结果并获取下一条命令 |
| `POST /api/browser/runs/{id}/heartbeat` | 心跳 |

命令类型：`goto`, `click`, `fill`, `select`, `extract`, `scroll`, `wait`, `snapshot`, `finish`, `noop`。

## 开发

- `content/content-script.js` — DOM 执行
- `background/service-worker.js` — 轮询与 Tab 协调
- 平台 schema：`src/ontology_platform/connector/browser/schema.py`
