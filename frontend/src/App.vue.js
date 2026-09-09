import { computed, ref } from "vue";
const topic = ref("生成式 AI 在教育行业的应用趋势");
const status = ref("idle");
const progress = ref(0);
const message = ref("准备开始一次新的研究");
const report = ref("");
const error = ref("");
const isRunning = computed(() => status.value !== "idle" && status.value !== "completed" && status.value !== "error");
async function startResearch() {
    if (!topic.value.trim() || isRunning.value)
        return;
    status.value = "planning";
    progress.value = 0;
    report.value = "";
    error.value = "";
    let receivedEvent = false;
    const source = new EventSource(`/api/research/stream?topic=${encodeURIComponent(topic.value.trim())}`);
    source.onmessage = (event) => {
        receivedEvent = true;
        let payload;
        try {
            payload = JSON.parse(event.data);
        }
        catch {
            source.close();
            status.value = "error";
            error.value = "后端返回了无法解析的 SSE 数据，请查看 FastAPI 控制台日志。";
            return;
        }
        status.value = payload.status;
        progress.value = payload.progress;
        message.value = payload.message;
        if (payload.report)
            report.value = payload.report;
        if (payload.status === "error") {
            source.close();
            error.value = payload.message;
        }
        else if (payload.status === "completed") {
            source.close();
        }
    };
    source.onerror = () => {
        source.close();
        if (receivedEvent && status.value === "error")
            return;
        if (status.value === "completed")
            return;
        status.value = "error";
        error.value = "无法建立 SSE 连接，请确认前端代理和 FastAPI 的 8000 端口均已启动。";
    };
}
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({
    ...{ class: "page-shell" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({
    ...{ class: "topbar" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "brand" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
    ...{ class: "brand-mark" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
    ...{ class: "connection" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.i)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
    ...{ class: "hero" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
    ...{ class: "eyebrow" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.em, __VLS_intrinsicElements.em)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
    ...{ class: "intro" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "research-card" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
    for: "topic",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.textarea)({
    ...{ onKeydown: (__VLS_ctx.startResearch) },
    id: "topic",
    value: (__VLS_ctx.topic),
    rows: "3",
    placeholder: "例如：量子计算对密码学的影响",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "card-footer" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
    ...{ class: "hint" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
    ...{ onClick: (__VLS_ctx.startResearch) },
    disabled: (__VLS_ctx.isRunning),
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
(__VLS_ctx.isRunning ? "研究中..." : "开始研究");
__VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
    ...{ class: "workspace" },
    ...{ class: ({ active: __VLS_ctx.status !== 'idle' }) },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "status-panel" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "section-heading" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
__VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
(__VLS_ctx.progress);
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "progress-track" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div)({
    ...{ style: ({ width: `${__VLS_ctx.progress}%` }) },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
    ...{ class: "status-message" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.span)({
    ...{ class: "pulse" },
});
(__VLS_ctx.message);
if (__VLS_ctx.error) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "error" },
    });
    (__VLS_ctx.error);
}
if (__VLS_ctx.report) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
        ...{ class: "report-panel" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "section-heading" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.pre, __VLS_intrinsicElements.pre)({});
    (__VLS_ctx.report);
}
/** @type {__VLS_StyleScopedClasses['page-shell']} */ ;
/** @type {__VLS_StyleScopedClasses['topbar']} */ ;
/** @type {__VLS_StyleScopedClasses['brand']} */ ;
/** @type {__VLS_StyleScopedClasses['brand-mark']} */ ;
/** @type {__VLS_StyleScopedClasses['connection']} */ ;
/** @type {__VLS_StyleScopedClasses['hero']} */ ;
/** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
/** @type {__VLS_StyleScopedClasses['intro']} */ ;
/** @type {__VLS_StyleScopedClasses['research-card']} */ ;
/** @type {__VLS_StyleScopedClasses['card-footer']} */ ;
/** @type {__VLS_StyleScopedClasses['hint']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace']} */ ;
/** @type {__VLS_StyleScopedClasses['active']} */ ;
/** @type {__VLS_StyleScopedClasses['status-panel']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['progress-track']} */ ;
/** @type {__VLS_StyleScopedClasses['status-message']} */ ;
/** @type {__VLS_StyleScopedClasses['pulse']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['report-panel']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            topic: topic,
            status: status,
            progress: progress,
            message: message,
            report: report,
            error: error,
            isRunning: isRunning,
            startResearch: startResearch,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
