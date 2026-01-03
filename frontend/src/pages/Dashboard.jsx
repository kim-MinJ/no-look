import { useEffect, useState, useCallback, useRef } from 'react';
import VideoPreview from '../components/VideoPreview';
import ConfigModal from '../components/ConfigModal';

import TransitionSelector from '../components/TransitionSelector';
import Toast, { useToast } from '../components/Toast';
import '../styles/dashboard.css';

import { wsClient } from '../lib/wsClient';
import { setPauseFake, setForceReal, resetLock, fetchEngineState, controlAssistant, requestMacroType } from '../lib/api';

import logoImg from '../assets/logo.png';

export default function Dashboard() {
    const { toasts, addToast, removeToast } = useToast();

    const [mode, setMode] = useState('REAL');
    const [ratio, setRatio] = useState(0);
    const [lockedFake, setLockedFake] = useState(false);
    const [pauseFake, setPauseFakeState] = useState(false);
    const [forceReal, setForceRealState] = useState(false);
    const [reasons, setReasons] = useState([]);
    const [sttData, setSttData] = useState({ history: [], current: '' });
    const [assistantEnabled, setAssistantEnabled] = useState(false);

    // ✅ session/warmup
    const [sessionActive, setSessionActive] = useState(false);
    const [warmingUp, setWarmingUp] = useState(false);
    const [warmupTotalSec, setWarmupTotalSec] = useState(30);
    const [warmupRemainingSec, setWarmupRemainingSec] = useState(0);

    const prevWarmingUpRef = useRef(false);
    const scrollRef = useRef(null);
    const [showConfigModal, setShowConfigModal] = useState(false);

    // ✅ Enter Key to send AI suggestion to Zoom
    useEffect(() => {
        const handleKeyDown = (e) => {
            // 다른 입력창(input, textarea 등)에 있을 때는 무시
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
                return;
            }

            // Enter 키 감지 (Shift/Alt 등 조합 제외, 추천 답변이 있을 때만)
            if (e.key === 'Enter' && sttData.suggestion && !e.shiftKey && !e.ctrlKey) {
                const sendMacro = async () => {
                    try {
                        console.log('🚀 Sending macro to zoom:', sttData.suggestion);
                        await requestMacroType(sttData.suggestion, false);
                        addToast('🚀 줌으로 답변을 전송했습니다!', 'info');
                    } catch (err) {
                        console.error('Failed to send macro:', err);
                        addToast('❌ 전송 실패: ' + err.message, 'error');
                    }
                };
                sendMacro();
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [sttData.suggestion, addToast]);

    // ✅ Smart Auto-scroll: Only scroll if the user is already near the bottom
    useEffect(() => {
        const el = scrollRef.current;
        if (!el) return;

        const isAtBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 100; // 100px threshold
        if (isAtBottom) {
            el.scrollTop = el.scrollHeight;
        }
    }, [sttData]);

    const mmss = (sec) => {
        const s = Math.max(0, Number(sec || 0));
        const m = String(Math.floor(s / 60)).padStart(2, '0');
        const r = String(Math.floor(s % 60)).padStart(2, '0');
        return `${m}:${r}`;
    };

    const applyState = useCallback((s) => {
        if (!s) return;

        setMode(s.mode ?? 'REAL');
        setRatio(s.ratio ?? 0);
        setLockedFake(!!s.lockedFake);
        setPauseFakeState(!!s.pauseFake);
        setForceRealState(!!s.forceReal);
        setReasons(s.reasons ?? []);
        if (s.stt) setSttData(s.stt);
        if (s.assistantEnabled !== undefined) setAssistantEnabled(!!s.assistantEnabled);

        setSessionActive(!!s.sessionActive);
        setWarmingUp(!!s.warmingUp);
        setWarmupTotalSec(s.warmupTotalSec ?? 30);
        setWarmupRemainingSec(s.warmupRemainingSec ?? 0);

        if (s.reaction) addToast(`🤖 ${s.reaction}`, 'success');
        if (s.notice) addToast(s.notice, 'success');

        const prev = prevWarmingUpRef.current;
        if (prev && !s.warmingUp) addToast('✅ 녹화 완료!', 'success');
        prevWarmingUpRef.current = !!s.warmingUp;
    }, [addToast]);

    useEffect(() => {
        fetchEngineState().then(applyState).catch(() => { });

        wsClient.onMessage = applyState;
        wsClient.connect();

        return () => {
            wsClient.disconnect();
            wsClient.onMessage = null;
        };
    }, [applyState]);

    const togglePauseFake = useCallback(async () => {
        const next = !pauseFake;
        const res = await setPauseFake(next);
        if (res.ok) addToast(`PauseFake: ${next ? 'ON' : 'OFF'}`, 'success');
    }, [pauseFake, addToast]);

    const toggleForceReal = useCallback(async () => {
        const next = !forceReal;
        const res = await setForceReal(next);
        if (res.ok) addToast(`ForceREAL: ${next ? 'ON' : 'OFF'}`, 'success');
    }, [forceReal, addToast]);

    const handleResetLock = useCallback(async () => {
        const res = await resetLock();
        if (res.ok) addToast('락 초기화 완료', 'success');
    }, [addToast]);

    const toggleAssistant = async () => {
        try {
            const newValue = !assistantEnabled;
            await controlAssistant(newValue);
            setAssistantEnabled(newValue);
        } catch (err) {
            console.error('Failed to toggle assistant:', err);
        }
    };

    const handleConfigSave = () => {
        addToast('⚙️ 설정이 저장되었습니다!', 'success');
    };

    const progress = warmupTotalSec > 0
        ? (warmupTotalSec - warmupRemainingSec) / warmupTotalSec
        : 0;

    const showWarmup = warmingUp || (sessionActive && warmupRemainingSec > 0);

    return (
        <div className="dashboard simple">
            {/* ✅ Warmup Overlay */}
            {showWarmup && (
                <div className="warmup-overlay">
                    <div className="warmup-card">
                        <img src={logoImg} alt="No-Look Logo" className="warmup-logo" />
                        <div className="warmup-title">녹화 중입니다</div>
                        <div className="warmup-desc">{warmupTotalSec}초 동안 가만히 있어주세요</div>
                        <div className="warmup-timer">{mmss(warmupRemainingSec)}</div>
                        <div className="warmup-bar">
                            <div
                                className="warmup-bar-fill"
                                style={{ width: `${Math.min(100, Math.max(0, progress * 100))}%` }}
                            />
                        </div>
                        <div className="warmup-sub">녹화가 끝나면 자동으로 추적을 시작해요.</div>
                    </div>
                </div>
            )}

            {/* ✅ 헤더 로고 */}
            <header className="dashboard-header">
                <img src={logoImg} alt="No-Look Logo" className="header-logo" />
            </header>

            <div className="simple-layout">
                <div className="video-section">
                    <VideoPreview mode={mode} ratio={ratio} addToast={addToast} />
                </div>

                <div className="control-bar">
                    <div className="switch-buttons">
                        <button className="btn btn-large btn-primary" onClick={togglePauseFake}>
                            {pauseFake ? 'FAKE 재생 재개' : 'FAKE 재생 일시정지'}
                        </button>

                        <button className="btn btn-large btn-secondary" onClick={toggleForceReal}>
                            {forceReal ? 'Force REAL 해제(자동복귀)' : 'Force REAL(강제복귀)'}
                        </button>

                        <button className="btn btn-large" onClick={handleResetLock}>
                            락 초기화
                        </button>

                        <button
                            className={`btn btn-large ${assistantEnabled ? 'btn-danger' : 'btn-success'}`}
                            style={{ marginLeft: 10 }}
                            onClick={toggleAssistant}
                        >
                            {assistantEnabled ? 'Auto Macro OFF' : 'Auto Macro ON'}
                        </button>
                        <button
                            className="btn btn-icon"
                            style={{ marginLeft: 8 }}
                            onClick={() => setShowConfigModal(true)}
                            title="설정"
                        >
                            ⚙️
                        </button>
                    </div>

                    <div className="mode-display">
                        <span className={`mode-indicator ${mode.toLowerCase()}`}>
                            현재: <strong>{mode}</strong> ({Math.round(ratio * 100)}%)
                        </span>
                        <span style={{ marginLeft: 12 }}>
                            Locked: <strong>{String(lockedFake)}</strong>
                        </span>
                        {!!reasons?.length && (
                            <span style={{ marginLeft: 12 }}>
                                Reasons: <strong>{reasons.join(', ')}</strong>
                            </span>
                        )}
                    </div>
                </div>

                <div className="transition-section">
                    <TransitionSelector addToast={addToast} />
                </div>

                {/* ✅ STT Display Section */}
                <div className="stt-section">
                    <h3 className="stt-title">
                        🎙️ Live Transcript (Auto Macro)
                    </h3>
                    <div
                        className="stt-history"
                        ref={scrollRef}
                    >
                        {sttData.history.length === 0 && !sttData.current && (
                            <div className="stt-empty">
                                대기 중... (말씀하시면 여기에 표시됩니다)
                            </div>
                        )}
                        {sttData.history.map((text, i) => (
                            <div key={i} className="stt-line">
                                {text}
                            </div>
                        ))}
                    </div>
                    {sttData.current && (
                        <div className="stt-current">
                            ▶ {sttData.current}
                        </div>
                    )}
                    {sttData.suggestion && (
                        <div className="stt-suggestion">
                            <span className="suggestion-label">
                                🤖 AI 추천 답변
                                <span className="suggestion-hint">Enter를 눌러 전송</span>
                            </span>
                            <div className="suggestion-content">{sttData.suggestion}</div>
                        </div>
                    )}
                </div>


            </div>

            <Toast toasts={toasts} onRemove={removeToast} />

            {/* 설정 모달 */}
            <ConfigModal
                isOpen={showConfigModal}
                onClose={() => setShowConfigModal(false)}
                onSave={handleConfigSave}
            />
        </div>
    );
}
