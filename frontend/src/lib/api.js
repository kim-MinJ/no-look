// src/lib/api.js

// DEV: Vite(5173)에서 FastAPI(8000)로 직접 붙기
// PROD: FastAPI가 React build 서빙할 때 same-origin(/api)
const API_BASE_URL = import.meta.env.DEV
    ? 'http://127.0.0.1:8000/api'
    : '/api';

async function fetchJson(url, options = {}) {
    const res = await fetch(url, options);
    const text = await res.text();

    let data = null;
    try {
        data = text ? JSON.parse(text) : null;
    } catch {
        // JSON 아닌 응답 대비
        data = { raw: text };
    }

    if (!res.ok) {
        const msg = data?.detail || data?.message || `${res.status} ${res.statusText}`;
        throw new Error(msg);
    }

    return data;
}

export async function setPauseFake(value) {
    return fetchJson(`${API_BASE_URL}/control/pause_fake`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
    });
}

export async function setForceReal(value) {
    return fetchJson(`${API_BASE_URL}/control/force_real`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
    });
}

export async function resetLock() {
    return fetchJson(`${API_BASE_URL}/control/reset_lock`, { method: 'POST' });
}

export async function fetchEngineState() {
    return fetchJson(`${API_BASE_URL}/state`);
}

export async function setTransitionEffect(effectName) {
    return fetchJson(`${API_BASE_URL}/control/transition`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: effectName }),
    });
}

export async function controlAssistant(value) {
    return fetchJson(`${API_BASE_URL}/control/assistant`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
    });
}

/**
 * ---- AI reply / macro ----
 * useMock=true면 프론트에서 더미로 동작.
 * useMock=false면 아래 엔드포인트로 요청(백엔드 구현되어 있어야 함):
 *  - POST /api/ai/reply  { text, tone } -> { candidates: string[] }
 *  - POST /api/macro/type { text } -> { success: boolean, message: string }
 */
export async function requestAiReply(transcript, tone = 'polite', useMock = true) {
    const text = (transcript || '').trim();
    if (!text) return { candidates: [] };

    if (useMock) {
        const base = text.slice(-80);
        const candidates =
            tone === 'short'
                ? ['넵 확인했습니다.', '좋습니다. 진행하겠습니다.', '네, 반영할게요.']
                : tone === 'casual'
                    ? ['ㅇㅋ! 바로 할게요', '좋아, 진행 ㄱㄱ', '확인~ 반영해둘게']
                    : [
                        '네, 확인했습니다. 해당 내용으로 진행하겠습니다.',
                        '확인했습니다. 필요한 부분 정리해서 반영하겠습니다.',
                        `네, 이해했습니다. (${base}) 이 방향으로 진행할게요.`,
                    ];
        return { candidates };
    }

    return fetchJson(`${API_BASE_URL}/ai/reply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, tone }),
    });
}

export async function requestMacroType(text, useMock = true) {
    const v = (text || '').trim();
    if (!v) return { success: false, message: '빈 텍스트입니다.' };

    if (useMock) {
        return { success: true, message: '(Mock) 채팅 입력 요청 완료' };
    }

    return fetchJson(`${API_BASE_URL}/macro/type`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: v }),
    });
}

// === Config management ===
export async function getConfig() {
    return fetchJson(`${API_BASE_URL}/config`);
}

export async function saveConfig(configData) {
    return fetchJson(`${API_BASE_URL}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configData),
    });
}
