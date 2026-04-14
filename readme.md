网页 URL 或上传视频 → 提取文本 → Kimi 按风格改写 →用户确认/编辑 → Edge TTS 生成语音 → 火山引擎数字人视频工作流
## 功能概览

| 模块 | 说明 |
|------|------|
| **数字人内容工作流** | 网页 URL 或上传视频 → **提取文本** → **Kimi 按风格改写** → **用户确认/编辑** → **Edge TTS 生成语音** → **火山引擎数字人视频**（后两步需在 `.env` 配置对应项）。 |
| **H5 页面** | 将上述工作流做成分步界面（提取 → 改写 → 确认 → 语音 → 视频），通过 Vite 开发服务器访问；接口经代理转发到本机 `8000` 端口后端。 |

## 环境要求

- Python **3.10+**
- **Node.js 18+**（仅在使用 `frontend/` H5 时需要，用于 `npm`）
- 网络（首次运行会下载嵌入模型；国内可在 `.env` 中配置 Hugging Face 镜像，见 `.env.example`）

## 安装与配置

1. **克隆或进入项目根目录**，创建并激活虚拟环境（示例）：

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   ```

2. **安装依赖**（依赖列表见 `pyproject.toml`）：

   ```bash
   pip install -e .
   ```

3. **配置 API Key**：复制环境变量模板并填写 **Moonshot API Key**：

   ```bash
   cp .env.example .env
   ```

   编辑 `.env`，至少设置 `MOONSHOT_API_KEY`。可选项（模型名、CORS、TTS、火山引擎数字人等）说明见 `.env.example` 内注释。

4. **（可选）安装 H5 前端依赖**：

   ```bash
   cd frontend && npm install && cd ..
   ```

## 启动方式

### 1. 后端：FastAPI（必须先启动，H5 与接口共用）

```bash
uvicorn server:app --host 127.0.0.1 --port 8000
```

- 接口文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>
- 局域网调试（手机连同一 Wi‑Fi 等）可将 `--host` 改为 `0.0.0.0`

公网部署时请自行增加鉴权、HTTPS 与限流等安全措施。

### 2. H5 页面：Vite 开发服务器（数字人工作流界面）

**须与上一步后端同时运行**：`frontend/vite.config.js` 已将 `/workflow`、`/rewrite-styles`、`/generated` 代理到 `http://127.0.0.1:8000`。

在项目根目录新开一个终端：

```bash
cd frontend
npm run dev
```

默认在浏览器打开：<http://127.0.0.1:5173/>

- **局域网用手机访问**：可先让后端 `uvicorn` 使用 `--host 0.0.0.0`；前端使用 `npm run dev -- --host`，并把 `vite.config.js` 里 `proxy` 的 `target` 从 `127.0.0.1` 改为你电脑的局域网 IP（与手机在同一网段）。
- 构建静态资源：`cd frontend && npm run build`，产物在 `frontend/dist/`。当前仓库未把 `dist` 挂到 FastAPI，生产环境可交给 Nginx 托管，或自行在 `server.py` 挂载静态目录并处理 API 跨域。

### 3. 终端对话（CLI，可选）

```bash
python main.py
```

首次启动会构建向量索引并可能下载嵌入模型。命令：`/agent` 切换角色、`quit` 退出。

---

更多实现细节见源码：`rag_chat.py`、`multi_agent.py`、`content_extraction.py`、`text_rewrite.py`、`tts_service.py`、`digital_human_service.py`；Web 入口为 `server.py`，H5 为 `frontend/src/App.vue`。


