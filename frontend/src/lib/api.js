const API_BASE_URL = 'http://127.0.0.1:8000';

export async function setPauseFake(value) {
    const res = await fetch(`${API_BASE_URL}/control/pause_fake`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
    });
    return res.json();
}

export async function setForceReal(value) {
    const res = await fetch(`${API_BASE_URL}/control/force_real`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
    });
    return res.json();
}


export async function resetLock() {
    const res = await fetch(`${API_BASE_URL}/control/reset_lock`, { method: 'POST' });
    return res.json();
}

export async function fetchEngineState() {
    const res = await fetch(`${API_BASE_URL}/state`);
    return res.json();
}

// ---- 아래는 너 기존 requestAiReply / requestMacroType 그대로 두면 됨 ----
export async function requestAiReply(transcript, tone = 'polite', useMock = true) {
    /* 기존 코드 그대로 */
}
export async function requestMacroType(text, useMock = true) {
    /* 기존 코드 그대로 */
}

export async function setTransitionEffect(effectName) {
    const res = await fetch(`${API_BASE_URL}/control/transition`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: effectName }),
    });
    return res.json();
}
