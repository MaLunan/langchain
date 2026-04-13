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
        :class="{ active: currentStep === i, done: currentStep > i }"
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

    <!-- ── 步骤 3：生成音频 ──────────────────────────── -->
    <div v-if="currentStep === 3" class="card">
      <div class="card-title">
        <span>🔊 生成语音</span>
        <span class="badge">步骤 4</span>
      </div>

      <div class="input-group">
        <label>待播报文本</label>
        <div class="result-box">{{ finalText }}</div>
      </div>

      <!-- 音频播放器 -->
      <template v-if="audioUrl">
        <div class="alert alert-success">✅ 音频生成成功</div>
        <audio :src="audioUrl" controls></audio>
      </template>

      <div class="btn-row">
        <button class="btn btn-outline" @click="currentStep = 2">← 修改文本</button>
        <button
          v-if="!audioUrl"
          class="btn btn-primary"
          :disabled="loading"
          @click="handleAudio"
        >
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? '生成中…' : '生成语音' }}</span>
        </button>
        <button v-if="audioUrl" class="btn btn-primary" @click="currentStep = 4">
          下一步：生成视频 →
        </button>
      </div>
    </div>

    <!-- ── 步骤 4：生成数字人视频 ───────────────────── -->
    <div v-if="currentStep === 4" class="card">
      <div class="card-title">
        <span>🤖 数字人视频</span>
        <span class="badge">步骤 5</span>
      </div>

      <template v-if="videoUrl">
        <div class="alert alert-success">🎉 视频生成成功！</div>
        <a :href="videoUrl" target="_blank" class="video-link">
          🎬 点击查看 / 下载视频
        </a>
      </template>
      <template v-else>
        <div class="alert alert-info">
          ⚡ 数字人视频生成通常需要 1-3 分钟，请耐心等待。
        </div>
        <div class="alert alert-info" style="margin-top:0">
          ⚙️ 需要在 .env 中配置 VOLCENGINE_ACCESS_KEY / SECRET_KEY / AVATAR_ID。
        </div>
      </template>

      <div class="btn-row">
        <button class="btn btn-outline" @click="currentStep = 3">← 返回音频</button>
        <button
          v-if="!videoUrl"
          class="btn btn-primary"
          :disabled="loading"
          @click="handleVideo"
        >
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? '生成中（请等待）…' : '生成数字人视频' }}</span>
        </button>
        <button v-if="videoUrl" class="btn btn-success" @click="reset">
          🔄 重新开始
        </button>
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
  { key: 'audio',   label: '生成语音' },
  { key: 'video',   label: '数字人视频' },
]

const STYLE_ICONS = { professional: '📋', casual: '💬', news: '📰' }

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
    const res = await generateVideo(sessionId.value)
    videoUrl.value    = res.video_url
    currentStep.value = 4
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function reset() {
  currentStep.value   = 0
  sessionId.value     = ''
  urlInput.value      = ''
  selectedFile.value  = null
  extractedText.value = ''
  editableText.value  = ''
  finalText.value     = ''
  audioUrl.value      = ''
  videoUrl.value      = ''
  error.value         = ''
}
</script>
