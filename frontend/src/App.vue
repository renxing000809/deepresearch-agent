<script setup lang="ts">
import { computed, ref } from "vue";

type EventPayload = { status: string; progress: number; message: string; report?: string };

const topic = ref("生成式 AI 在教育行业的应用趋势");
const status = ref("idle");
const progress = ref(0);
const message = ref("准备开始一次新的研究");
const report = ref("");
const error = ref("");
const isRunning = computed(() => status.value !== "idle" && status.value !== "completed" && status.value !== "error");

async function startResearch() {
  if (!topic.value.trim() || isRunning.value) return;
  status.value = "planning";
  progress.value = 0;
  report.value = "";
  error.value = "";
  let receivedEvent = false;
  const source = new EventSource(`/api/research/stream?topic=${encodeURIComponent(topic.value.trim())}`);
  source.onmessage = (event) => {
    receivedEvent = true;
    let payload: EventPayload;
    try {
      payload = JSON.parse(event.data) as EventPayload;
    } catch {
      source.close();
      status.value = "error";
      error.value = "后端返回了无法解析的 SSE 数据，请查看 FastAPI 控制台日志。";
      return;
    }
    status.value = payload.status;
    progress.value = payload.progress;
    message.value = payload.message;
    if (payload.report) report.value = payload.report;
    if (payload.status === "error") {
      source.close();
      error.value = payload.message;
    } else if (payload.status === "completed") {
      source.close();
    }
  };
  source.onerror = () => {
    source.close();
    if (receivedEvent && status.value === "error") return;
    if (status.value === "completed") return;
    status.value = "error";
    error.value = "无法建立 SSE 连接，请确认前端代理和 FastAPI 的 8000 端口均已启动。";
  };
}
</script>

<template>
  <main class="page-shell">
    <header class="topbar">
      <div class="brand"><span class="brand-mark">DR</span><span>Deep Research</span></div>
      <span class="connection"><i /> API 已连接</span>
    </header>
    <section class="hero">
      <p class="eyebrow">AUTOMATED KNOWLEDGE WORKSPACE</p>
      <h1>把一个问题，<em>研究透。</em></h1>
      <p class="intro">输入你想深入了解的主题，智能助手会规划方向、梳理资料，并生成一份结构清晰的研究报告。</p>
      <div class="research-card">
        <label for="topic">研究主题</label>
        <textarea id="topic" v-model="topic" rows="3" placeholder="例如：量子计算对密码学的影响" @keydown.ctrl.enter="startResearch" />
        <div class="card-footer">
          <span class="hint">Ctrl + Enter 开始研究</span>
          <button :disabled="isRunning" @click="startResearch"><span>{{ isRunning ? "研究中..." : "开始研究" }}</span><b>↗</b></button>
        </div>
      </div>
    </section>
    <section class="workspace" :class="{ active: status !== 'idle' }">
      <div class="status-panel">
        <div class="section-heading"><span>研究进度</span><strong>{{ progress }}%</strong></div>
        <div class="progress-track"><div :style="{ width: `${progress}%` }" /></div>
        <p class="status-message"><span class="pulse" />{{ message }}</p>
        <p v-if="error" class="error">{{ error }}</p>
      </div>
      <article v-if="report" class="report-panel">
        <div class="section-heading"><span>研究报告</span><small>已生成</small></div>
        <pre>{{ report }}</pre>
      </article>
    </section>
  </main>
</template>
