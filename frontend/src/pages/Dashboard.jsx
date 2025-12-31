import { useEffect, useState, useCallback, useRef } from 'react';
import VideoPreview from '../components/VideoPreview';
import SttPanel from '../components/SttPanel';
import Toast, { useToast } from '../components/Toast';
import '../styles/dashboard.css';

import { wsClient } from '../lib/wsClient';
import { setPauseFake, setForceReal, resetLock, fetchEngineState } from '../lib/api';

export default function Dashboard() {
    const { toasts, addToast, removeToast } = useToast();

    const [mode, setMode] = useState('REAL');
    const [ratio, setRatio] = useState(0);
    const [lockedFake, setLockedFake] = useState(false);
    const [pauseFake, setPauseFakeState] = useState(false);
    const [forceReal, setForceRealState] = useState(false);
    const [reasons, setReasons] = useState([]);

    // ✅ warmup UI
    const [warmingUp, setWarmingUp] = useState(false);
    const [warmupTotalSec, setWarmupTotalSec] = useState(120);      // ✅ 2분
    const [warmupRemainingSec, setWarmupRemainingSec] = useState(0);

    const prevWarmingUpRef = useRef(false);

    const mmss = (sec) => {
        const s = Math.max(0, Number(sec || 0));
        const m = String(Math.floor(s / 60)).padStart(2, '0');
        const r = String(Math.floor(s % 60)).padStart(2, '0');
        return `${m}:${r}`;
    };

    useEffect(() => {
        fetchEngineState()
            .then((s) => {
                setMode(s.mode ?? 'REAL');
                setRatio(s.ratio ?? 0);
                setLockedFake(!!s.lockedFake);
                setPauseFakeState(!!s.pauseFake);
                setForceRealState(!!s.forceReal);
                setReasons(s.reasons ?? []);

                setWarmingUp(!!s.warmingUp);
                setWarmupTotalSec(s.warmupTotalSec ?? 120);
                setWarmupRemainingSec(s.warmupRemainingSec ?? 0);
            })
            .catch(() => {});

        wsClient.onMessage = (s) => {
            if (!s) return;

            setMode(s.mode ?? 'REAL');
            setRatio(s.ratio ?? 0);
            setLockedFake(!!s.lockedFake);
            setPauseFakeState(!!s.pauseFake);
            setForceRealState(!!s.forceReal);
            setReasons(s.reasons ?? []);

            setWarmingUp(!!s.warmingUp);
            setWarmupTotalSec(s.warmupTotalSec ?? 120);
            setWarmupRemainingSec(s.warmupRemainingSec ?? 0);

            // 락 처음 걸릴 때 reaction 오면 토스트
            if (s.reaction) addToast(`🤖 ${s.reaction}`, 'success');

            // ✅ warmup 완료 공지(백엔드 notice)
            if (s.notice) addToast(s.notice, 'success');

            // ✅ 혹시 notice 못 받아도 "warmingUp true -> false"로 완료 토스트
            const prev = prevWarmingUpRef.current;
            if (prev && !s.warmingUp) {
                addToast('✅ 녹화 완료!', 'success');
            }
            prevWarmingUpRef.current = !!s.warmingUp;
        };

        wsClient.connect();

        return () => {
            wsClient.disconnect();
            wsClient.onMessage = null;
        };
    }, [addToast]);

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

    const progress = warmupTotalSec > 0 ? (warmupTotalSec - warmupRemainingSec) / warmupTotalSec : 0;

    return (
        <div className="dashboard simple">
            {/* ✅ Warmup Overlay */}
            {warmingUp && (
                <div className="warmup-overlay">
                    <div className="warmup-card">
                        <div className="warmup-title">녹화 중입니다</div>
                        <div className="warmup-desc">{warmupTotalSec}초 동안 가만히 있어주세요</div>
                        <div className="warmup-timer">{mmss(warmupRemainingSec)}</div>
                        <div className="warmup-bar">
                            <div className="warmup-bar-fill" style={{ width: `${Math.min(100, Math.max(0, progress * 100))}%` }} />
                        </div>
                        <div className="warmup-sub">녹화가 끝나면 자동으로 추적을 시작해요.</div>
                    </div>
                </div>
            )}

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

                <div className="stt-section">
                    <SttPanel addToast={addToast} />
                </div>
            </div>

            <Toast toasts={toasts} onRemove={removeToast} />
        </div>
    );
}
