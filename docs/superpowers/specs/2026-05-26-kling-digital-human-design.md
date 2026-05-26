# 可灵 AI 数字人 / 文生视频集成设计

**日期：** 2026-05-26
**状态：** 已批准

---

## 背景

现有工作流使用火山引擎数字人 API，路径固定为「TTS 音频 → 数字人视频」。本次改造：

1. 将底层服务切换为**可灵 AI（Kling AI）**
2. 新增**文生视频**路径，用户在确认文本后可自由选择两种生成模式

---

## 工作流

```
提取内容 → AI 改写 → 确认文本 → 选择模式
                                    ├─ A 数字人口播：生成 TTS 音频 → 可灵 lip-sync → 视频
                                    └─ B 文生视频：  直接调用可灵 text2video → 视频
```

---

## 模块变更

### 1. 新文件 `kling_service.py`（替换 `digital_human_service.py`）

**职责：** 封装所有可灵 API 调用，对外暴露两个函数。

**鉴权：** JWT HS256
- Header: `{"alg": "HS256", "typ": "JWT"}`
- Payload: `{"iss": KLING_ACCESS_KEY_ID, "exp": now+1800, "nbf": now-5}`
- Secret: `KLING_ACCESS_KEY_SECRET`
- 请求头: `Authorization: Bearer <token>`

**公开接口：**

```python
def generate_avatar_video(
    audio_path: Path,
    avatar_id: str | None = None,  # None 时读 KLING_AVATAR_ID
) -> str:
    """模式 A：上传音频 → 提交数字人口播任务 → 轮询 → 返回视频 URL"""

def generate_text_to_video(
    text: str,
    model: str = "kling-v1",       # 可选 kling-v1-5
    duration: int = 5,             # 5 或 10（秒）
    aspect_ratio: str = "16:9",
    mode: str = "std",             # std / pro
) -> str:
    """模式 B：提交文生视频任务 → 轮询 → 返回视频 URL"""
```

**内部辅助：**
- `_make_jwt(ak, sk) -> str`
- `_poll_task(task_id, timeout=300) -> str`：通用轮询，`GET /v1/videos/{task_id}`，等待 `succeed`，每 5 秒一次

**API 端点：**
- 数字人口播：`POST https://api.klingai.com/v1/videos/lip-sync`（或 avatar 接口，按实际文档参数对齐）
- 文生视频：`POST https://api.klingai.com/v1/videos/text2video`
- 任务查询：`GET https://api.klingai.com/v1/videos/{task_id}`

> 注：若可灵接口实际路径与上述不符，仅需修改 `kling_service.py` 内的常量，不影响其他模块。

---

### 2. `workflow_state.py`

新增字段：

```python
video_mode: str = ""   # "avatar" | "text2video"，在模式选择步骤写入
```

`WorkflowStep` 枚举新增：

```python
MODE_SELECTED = "mode_selected"
```

---

### 3. `server.py`

**`POST /workflow/{id}/video`** 接受 body：

```json
{ "mode": "avatar" | "text2video" }
```

逻辑：
- `avatar`：校验 `state.audio_path` 存在 → 调用 `generate_avatar_video`
- `text2video`：校验 `state.final_text` 非空 → 调用 `generate_text_to_video`
- 两条路径都写入 `state.video_url`，设置 `WorkflowStep.VIDEO_DONE`

**`POST /workflow/{id}/audio`** 不变，仍可独立调用（Mode A 需要先调此接口）。

---

### 4. 前端 `frontend/src/App.vue`

**步骤定义变更：**

```
0: 提取内容
1: AI 改写
2: 确认文本
3: 选择模式         ← 新增
4: 生成音频         ← 仅 Mode A 显示（Mode B 跳过）
5: 生成视频
```

步骤指示器始终显示 6 步，Mode B 时"生成音频"标记为"已跳过"（灰色）。

**步骤 3 UI（选择模式）：**

```
┌──────────────────────────────────────────┐
│  选择生成方式                              │
│                                          │
│  ┌──────────────┐  ┌──────────────────┐  │
│  │  🎙️ 数字人口播 │  │   🎬 文生视频     │  │
│  │ TTS → 数字人  │  │  文字直接生成     │  │
│  └──────────────┘  └──────────────────┘  │
│                                          │
│  [← 修改文本]          [下一步 →]         │
└──────────────────────────────────────────┘
```

**步骤 5 UI（生成视频）：**
Mode A 时显示"调用可灵数字人口播"；Mode B 时显示文生视频参数（时长、比例可选）。

**`src/api/workflow.js`** 更新现有 `generateVideo`：

```js
// 原签名: generateVideo(sessionId)
// 新签名: generateVideo(sessionId, mode, params = {})
export async function generateVideo(sessionId, mode, params = {}) {
  // POST /workflow/{id}/video  body: { mode, ...params }
}
```

---

### 5. 环境变量（`.env`）

```
# 可灵 AI（替换 Volcengine 配置）
KLING_ACCESS_KEY_ID=
KLING_ACCESS_KEY_SECRET=
KLING_AVATAR_ID=          # 模式 A 需要，可灵后台创建的形象 ID
```

`digital_human_service.py` 保留但不再被调用，待后续确认删除。

---

## 错误处理

| 情形 | HTTP 状态 | 提示 |
|---|---|---|
| 缺少 KLING_ACCESS_KEY_ID/SECRET | 503 | 请配置可灵 API 密钥 |
| Mode A 未先生成音频 | 409 | 请先生成音频 |
| 可灵任务失败/超时 | 500 | 包含原始错误信息 |
| 模式参数非法 | 422 | mode 必须为 avatar 或 text2video |

---

## 不在本次范围内

- 删除旧 `digital_human_service.py`（保留备用）
- 文生视频高级参数（负向提示词、cfg_scale）暂不暴露到前端
- 可灵 image2video 接口
