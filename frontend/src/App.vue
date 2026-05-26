<template>
  <div>
    <!-- 页头 -->
    <div style="text-align:center;padding:32px 0 8px">
      <h1 style="font-size:24px;font-weight:800;color:#1a1a2e">数字人内容生成工作流</h1>
      <p style="color:#888;font-size:13px;margin-top:6px">
        提取文本 → AI 改写 → 生成语音 → 数字人视频
      </p>
    </div>

    <!-- 步骤指示器 -->
    <div class="stepper">
      <div
        v-for="(s, i) in STEPS"
        :key="s.key"
        class="step-item"
        :class="{ active: currentStep === i, done: isStepDone(i) }"
      >
        <div class="step-dot">
          <span v-if="currentStep > i">✓</span>
          <span v-else>{{ i + 1 }}</span>
        </div>
        <div class="step-label">{{ s.label }}</div>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="alert alert-error">
      <span>⚠️</span>
      <span>{{ error }}</span>
    </div>

    <!-- ── 步骤 0：提取内容 ──────────────────────────── -->
    <div v-if="currentStep === 0" class="card">
      <div class="card-title">
        <span>📥 提取内容</span>
        <span class="badge">步骤 1</span>
      </div>

      <!-- 来源切换 -->
      <div class="tabs">
        <button
          class="tab-btn"
          :class="{ active: sourceMode === 'url' }"
          @click="sourceMode = 'url'"
        >🔗 网页链接</button>
        <button
          class="tab-btn"
          :class="{ active: sourceMode === 'file' }"
          @click="sourceMode = 'file'"
        >🎬 视频文件</button>
      </div>

      <!-- URL 输入 -->
      <template v-if="sourceMode === 'url'">
        <div class="input-group">
          <label>网页 URL</label>
          <input
            v-model="urlInput"
            type="url"
            placeholder="https://example.com/article"
          />
        </div>
      </template>

      <!-- 文件上传 -->
      <template v-else>
        <div
          class="upload-area"
          :class="{ 'drag-over': isDragOver }"
          @click="$refs.fileInput.click()"
          @dragover.prevent="isDragOver = true"
          @dragleave="isDragOver = false"
          @drop.prevent="onDrop"
        >
          <input ref="fileInput" type="file" accept="video/*" @change="onFileChange" />
          <div class="upload-icon">🎬</div>
          <div v-if="selectedFile" class="upload-name">{{ selectedFile.name }}</div>
          <p v-else>点击选择或拖拽视频文件<br><small>支持 MP4 / MOV / AVI / MKV 等</small></p>
        </div>
      </template>

      <div class="btn-row">
        <button
          class="btn btn-primary"
          :disabled="loading || (sourceMode === 'url' ? !urlInput.trim() : !selectedFile)"
          @click="handleExtract"
        >
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? '提取中…' : '开始提取' }}</span>
        </button>
      </div>
    </div>

    <!-- ── 步骤 1：改写文本 ──────────────────────────── -->
    <div v-if="currentStep === 1" class="card">
      <div class="card-title">
        <span>✏️ AI 改写</span>
        <span class="badge">步骤 2</span>
      </div>

      <!-- 原文预览 -->
      <div class="input-group">
        <label>原始提取文本</label>
        <div class="result-box">{{ extractedText }}</div>
      </div>

      <!-- 改写风格选择 -->
      <div class="input-group">
        <label>选择改写风格</label>
        <div class="style-grid">
          <div
            v-for="s in rewriteStyles"
            :key="s.style_id"
            class="style-card"
            :class="{ selected: selectedStyle === s.style_id }"
            @click="selectedStyle = s.style_id"
          >
            <div class="style-icon">{{ STYLE_ICONS[s.style_id] || '📝' }}</div>
            <div class="style-name">{{ s.display_name }}</div>
          </div>
        </div>
      </div>

      <div class="btn-row">
        <button class="btn btn-outline" @click="currentStep = 0">← 重新提取</button>
        <button
          class="btn btn-primary"
          :disabled="loading || !selectedStyle"
          @click="handleRewrite"
        >
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? '改写中…' : 'AI 改写' }}</span>
        </button>
      </div>
    </div>

    <!-- ── 步骤 2：确认文本 ──────────────────────────── -->
    <div v-if="currentStep === 2" class="card">
      <div class="card-title">
        <span>✅ 确认文本</span>
        <span class="badge">步骤 3</span>
      </div>

      <div class="input-group">
        <label>改写结果（可直接编辑修改）</label>
        <textarea
          v-model="editableText"
          class="result-box editable"
          rows="10"
          style="border:1.5px solid #ddd;"
        ></textarea>
      </div>

      <div class="btn-row">
        <button class="btn btn-outline" @click="currentStep = 1">← 重新改写</button>
        <button
          class="btn btn-success"
          :disabled="loading || !editableText.trim()"
          @click="handleConfirm"
        >
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? '保存中…' : '确认文本' }}</span>
        </button>
      </div>
    </div>

    <!-- ── 步骤 3：选择模式 ──────────────────────────── -->
    <div v-if="currentStep === 3" class="card">
      <div class="card-title">
        <span>🎯 选择生成方式</span>
        <span class="badge">步骤 4</span>
      </div>

      <div class="mode-grid">
        <div
          class="mode-card"
          :class="{ selected: videoMode === 'avatar' }"
          @click="videoMode = 'avatar'"
        >
          <div class="mode-icon">🎙️</div>
          <div class="mode-title">数字人口播</div>
          <div class="mode-desc">生成 TTS 音频，再驱动数字人对嘴播报</div>
        </div>
        <div
          class="mode-card"
          :class="{ selected: videoMode === 'text2video' }"
          @click="videoMode = 'text2video'"
        >
          <div class="mode-icon">🎬</div>
          <div class="mode-title">文生视频</div>
          <div class="mode-desc">直接将文字交给可灵 AI 生成视频，无需音频</div>
        </div>
      </div>

      <template v-if="videoMode === 'text2video'">
        <div class="input-group" style="margin-top:16px">
          <label>视频时长</label>
          <div class="tabs" style="width:fit-content">
            <button class="tab-btn" :class="{ active: t2vDuration === 5 }" @click="t2vDuration = 5">5 秒</button>
            <button class="tab-btn" :class="{ active: t2vDuration === 10 }" @click="t2vDuration = 10">10 秒</button>
          </div>
        </div>
        <div class="input-group">
          <label>画面比例</label>
          <div class="tabs" style="width:fit-content">
            <button class="tab-btn" :class="{ active: t2vAspectRatio === '16:9' }" @click="t2vAspectRatio = '16:9'">16:9</button>
            <button class="tab-btn" :class="{ active: t2vAspectRatio === '9:16' }" @click="t2vAspectRatio = '9:16'">9:16</button>
            <button class="tab-btn" :class="{ active: t2vAspectRatio === '1:1' }" @click="t2vAspectRatio = '1:1'">1:1</button>
          </div>
        </div>
      </template>

      <div class="btn-row">
        <button class="btn btn-outline" @click="currentStep = 2">← 修改文本</button>
        <button
          class="btn btn-primary"
          :disabled="!videoMode"
          @click="handleModeSelect"
        >
          下一步 →
        </button>
      </div>
    </div>

    <!-- ── 步骤 4：生成音频（仅 Mode A）───────────────── -->
    <div v-if="currentStep === 4" class="card">
      <div class="card-title">
        <span>🔊 生成语音</span>
        <span class="badge">步骤 5</span>
      </div>

      <div class="input-group">
        <label>待播报文本</label>
        <div class="result-box">{{ finalText }}</div>
      </div>

      <template v-if="audioUrl">
        <div class="alert alert-success">✅ 音频生成成功</div>
        <audio :src="audioUrl" controls></audio>
      </template>

      <div class="btn-row">
        <button class="btn btn-outline" @click="currentStep = 3">← 重新选择</button>
        <button v-if="!audioUrl" class="btn btn-primary" :disabled="loading" @click="handleAudio">
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? '生成中…' : '生成语音' }}</span>
        </button>
        <button v-if="audioUrl" class="btn btn-primary" @click="currentStep = 5">
          下一步：生成视频 →
        </button>
      </div>
    </div>

    <!-- ── 步骤 5：生成视频 ───────────────────────────── -->
    <div v-if="currentStep === 5" class="card">
      <div class="card-title">
        <span>{{ videoMode === 'avatar' ? '🤖 数字人视频' : '🎬 文生视频' }}</span>
        <span class="badge">步骤 6</span>
      </div>

      <template v-if="videoUrl">
        <div class="alert alert-success">🎉 视频生成成功！</div>
        <a :href="videoUrl" target="_blank" class="video-link">🎬 点击查看 / 下载视频</a>
      </template>
      <template v-else>
        <div class="alert alert-info">
          ⚡ {{ videoMode === 'avatar' ? '数字人口播' : '文生视频' }}生成通常需要 1-3 分钟，请耐心等待。
        </div>
        <div v-if="videoMode === 'text2video'" class="alert alert-info" style="margin-top:0">
          📝 时长：{{ t2vDuration }}s　比例：{{ t2vAspectRatio }}
        </div>
        <div class="alert alert-info" style="margin-top:0">
          ⚙️ 需要在 .env 中配置 KLING_ACCESS_KEY_ID / KLING_ACCESS_KEY_SECRET{{ videoMode === 'avatar' ? ' / KLING_AVATAR_ID' : '' }}
        </div>
      </template>

      <div class="btn-row">
        <button class="btn btn-outline" @click="currentStep = videoMode === 'avatar' ? 4 : 3">← 返回</button>
        <button v-if="!videoUrl" class="btn btn-primary" :disabled="loading" @click="handleVideo">
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? '生成中（请等待）…' : (videoMode === 'avatar' ? '生成数字人视频' : '文生视频') }}</span>
        </button>
        <button v-if="videoUrl" class="btn btn-success" @click="reset">🔄 重新开始</button>
      </div>
    </div>

    <!-- 会话信息 -->
    <div v-if="sessionId" style="text-align:center;color:#bbb;font-size:11px;margin-top:4px">
      session: {{ sessionId }}
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import {
  uploadVideo,
  startWorkflow,
  fetchRewriteStyles,
  rewriteText,
  confirmText,
  generateAudio,
  generateVideo,
} from './api/workflow.js'

const STEPS = [
  { key: 'extract', label: '提取内容' },
  { key: 'rewrite', label: 'AI 改写' },
  { key: 'confirm', label: '确认文本' },
  { key: 'mode',    label: '选择模式' },
  { key: 'audio',   label: '生成语音' },
  { key: 'video',   label: '生成视频' },
]

const STYLE_ICONS = { professional: '📋', casual: '💬', news: '📰' }

function isStepDone(i) {
  if (currentStep.value > i) return true
  if (i === 4 && videoMode.value === 'text2video' && currentStep.value >= 5) return true
  return false
}

// ── 状态 ────────────────────────────────────────────────
const currentStep  = ref(0)
const loading      = ref(false)
const error        = ref('')

const sourceMode   = ref('url')
const urlInput     = ref('')
const selectedFile = ref(null)
const isDragOver   = ref(false)

const sessionId    = ref('')
const extractedText = ref('')
const rewriteStyles = ref([])
const selectedStyle = ref('')
const editableText  = ref('')
const finalText     = ref('')
const audioUrl      = ref('')
const videoUrl      = ref('')
const videoMode      = ref('')
const t2vDuration    = ref(5)
const t2vAspectRatio = ref('16:9')

onMounted(async () => {
  try {
    rewriteStyles.value = await fetchRewriteStyles()
    if (rewriteStyles.value.length) selectedStyle.value = rewriteStyles.value[0].style_id
  } catch { /* 后端未启动时静默失败 */ }
})

// ── 文件选择 ─────────────────────────────────────────────
function onFileChange(e) {
  selectedFile.value = e.target.files[0] || null
}
function onDrop(e) {
  isDragOver.value = false
  const f = e.dataTransfer.files[0]
  if (f && f.type.startsWith('video/')) selectedFile.value = f
}

// ── 步骤处理函数 ─────────────────────────────────────────
async function handleExtract() {
  error.value = ''
  loading.value = true
  try {
    let source = ''
    if (sourceMode.value === 'url') {
      source = urlInput.value.trim()
    } else {
      const up = await uploadVideo(selectedFile.value)
      source = up.file_path
    }
    const res = await startWorkflow(source)
    sessionId.value    = res.session_id
    extractedText.value = res.extracted_text
    currentStep.value  = 1
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function handleRewrite() {
  error.value = ''
  loading.value = true
  try {
    const res = await rewriteText(sessionId.value, selectedStyle.value)
    editableText.value = res.rewritten_text
    currentStep.value  = 2
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function handleConfirm() {
  error.value = ''
  loading.value = true
  try {
    const res = await confirmText(sessionId.value, editableText.value)
    finalText.value   = res.final_text
    currentStep.value = 3
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function handleModeSelect() {
  if (videoMode.value === 'avatar') {
    currentStep.value = 4
  } else {
    currentStep.value = 5
  }
}

async function handleAudio() {
  error.value = ''
  loading.value = true
  try {
    const res = await generateAudio(sessionId.value)
    audioUrl.value = res.audio_url
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function handleVideo() {
  error.value = ''
  loading.value = true
  try {
    const params = videoMode.value === 'text2video'
      ? { duration: t2vDuration.value, aspect_ratio: t2vAspectRatio.value }
      : {}
    const res = await generateVideo(sessionId.value, videoMode.value, params)
    videoUrl.value = res.video_url
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function reset() {
  currentStep.value    = 0
  sessionId.value      = ''
  urlInput.value       = ''
  selectedFile.value   = null
  extractedText.value  = ''
  editableText.value   = ''
  finalText.value      = ''
  audioUrl.value       = ''
  videoUrl.value       = ''
  videoMode.value      = ''
  t2vDuration.value    = 5
  t2vAspectRatio.value = '16:9'
  error.value          = ''
}
</script>

<style>
.mode-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin: 16px 0;
}
.mode-card {
  border: 2px solid #e5e7eb;
  border-radius: 12px;
  padding: 24px 16px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.mode-card:hover { border-color: #6366f1; }
.mode-card.selected { border-color: #6366f1; background: #f0f0ff; }
.mode-icon { font-size: 32px; margin-bottom: 8px; }
.mode-title { font-weight: 700; font-size: 15px; margin-bottom: 4px; }
.mode-desc { font-size: 12px; color: #888; line-height: 1.5; }
</style>
