import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import VideoPreview from '../components/VideoPreview';
import SttPanel from '../components/SttPanel';
import Toast, { useToast } from '../components/Toast';
import '../styles/dashboard.css';

import { wsClient } from '../lib/wsClient';
import { setPauseFake, setForceReal, resetLock, fetchEngineState } from '../lib/api';

function formatMMSS(totalSec) {
    const s = Math.max(0, Number(totalSec || 0));
    const mm = String(Math.floor(s / 60)).padStart(2, '0');
    const ss = String(Math.floor(s % 60)).padStart(2, '0');
    return `${mm}:${ss}`;
}

export default function Dashboard() {
    const { toasts, addToast, removeToast } = useToast();

    const [mode, setMode] = useState('REAL');
    const [ratio, setRatio] = useState(0);
    const [lockedFake, setLockedFake] = useState(false);
    const [pauseFake, setPauseFakeState] = useState(false);
    const [forceReal, setForceRealState] = useState(false);
    const [reasons, setReasons] = useState([]);

    // ✅ Warmup UI states (백엔드 state에 추가된 값 사용)
    const [warmup, setWarmup] = useState(false);
    const [warmupRemainingSec, setWarmupRemainingSec] = useState(0);
    const [trackingEnabled, setTrackingEnabled] = useState(true);
    const [fakeSource, setFakeSource] = useState('sample');

    // warmup 종료 감지용
    const prevWarmupRef = useRef(null);

    const warmupTimeText = useMemo(
        () => formatMMSS(warmupRemainingSec),
        [warmupRemainingSec]
    );

    // WS connect
    useEffect(() => {
        // 초기 상태 한번 가져오기(WS 오기 전)
        fetchEngineState()
            .then((s) => {
                setMode(s.mode ?? 'REAL');
                setRatio(s.ratio ?? 0);
                setLockedFake(!!s.lockedFake);
                setPauseFakeState(!!s.pauseFake);
                setForceRealState(!!s.forceReal);
                setReasons(s.reasons ?? []);

                // ✅ warmup fields
                setWarmup(!!s.warmup);
                setWarmupRemainingSec(s.warmupRemainingSec ?? 0);
                setTrackingEnabled(s.trackingEnabled ?? true);
                setFakeSource(s.fakeSource ?? 'sample');
                prevWarmupRef.current = !!s.warmup;
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

            // ✅ warmup fields
            const nextWarmup = !!s.warmup;
            setWarmup(nextWarmup);
            setWarmupRemainingSec(s.warmupRemainingSec ?? 0);
            setTrackingEnabled(s.trackingEnabled ?? true);
            setFakeSource(s.fakeSource ?? 'sample');

            // ✅ warmup 끝난 순간: 토스트
            const prevWarmup = prevWarmupRef.current;
            if (prevWarmup === true && nextWarmup === false) {
                addToast('✅ 5분 녹화 완료! 이제 방금 녹화한 영상으로 자연스럽게 FAKE 재생 가능', 'success');
            }
            prevWarmupRef.current = nextWarmup;

            // 락 처음 걸릴 때 reaction 오면 토스트
            if (s.reaction) addToast(`🤖 ${s.reaction}`, 'success');
        };

        wsClient.connect();

        return () => {
            wsClient.disconnect();
            wsClient.onMessage = null;
        };
    }, [addToast]);

    // Controls
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

    // ✅ 워밍업 중엔 조작 막기(원치 않으면 disabled 제거해도 됨)
    const controlsDisabled = warmup === true;

    return (
        <div className="dashboard simple">
            <div className="simple-layout">

                {/* ✅ WARMUP BANNER */}
                {warmup && (
                    <div
                        style={{
                            background: 'rgba(245, 158, 11, 0.15)',
                            border: '1px solid rgba(245, 158, 11, 0.35)',
                            color: 'var(--text-primary)',
                            borderRadius: '12px',
                            padding: '12px 14px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: 12,
                        }}
                    >
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <div style={{ fontWeight: 700 }}>
                                ⏺️ 5분 동안은 가만히 있어주세요 — 녹화 중입니다
                            </div>
                            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                                워밍업 중에는 추적이 꺼져 있어요 (tracking OFF) · 완료되면 자동으로 녹화본을 FAKE로 사용합니다
                            </div>
                        </div>

                        <div style={{ textAlign: 'right', minWidth: 120 }}>
                            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>남은 시간</div>
                            <div style={{ fontSize: 20, fontWeight: 800 }}>{warmupTimeText}</div>
                        </div>
                    </div>
                )}

                {/* ✅ Optional: warmup 끝난 뒤 “완료” 표시(토스트 말고 화면에도) */}
                {!warmup && fakeSource === 'warmup' && (
                    <div
                        style={{
                            background: 'rgba(34, 197, 94, 0.12)',
                            border: '1px solid rgba(34, 197, 94, 0.35)',
                            color: 'var(--text-primary)',
                            borderRadius: '12px',
                            padding: '10px 14px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: 12,
                        }}
                    >
                        <div style={{ fontWeight: 700 }}>✅ 녹화 완료 — 방금 녹화한 5분 영상으로 FAKE 재생 준비됨</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                            tracking: {trackingEnabled ? 'ON' : 'OFF'} · source: {fakeSource}
                        </div>
                    </div>
                )}

                <div className="video-section">
                    <VideoPreview mode={mode} ratio={ratio} addToast={addToast} />
                </div>

                <div className="control-bar">
                    <div className="switch-buttons">
                        <button
                            className="btn btn-large btn-primary"
                            onClick={togglePauseFake}
                            disabled={controlsDisabled}
                            title={controlsDisabled ? '워밍업 녹화 중에는 조작이 잠깐 비활성화됩니다' : ''}
                        >
                            {pauseFake ? 'FAKE 재생 재개' : 'FAKE 재생 일시정지'}
                        </button>

                        <button
                            className="btn btn-large btn-secondary"
                            onClick={toggleForceReal}
                            disabled={controlsDisabled}
                            title={controlsDisabled ? '워밍업 녹화 중에는 조작이 잠깐 비활성화됩니다' : ''}
                        >
                            {forceReal ? 'Force REAL 해제(자동복귀)' : 'Force REAL(강제복귀)'}
                        </button>

                        <button
                            className="btn btn-large"
                            onClick={handleResetLock}
                            disabled={controlsDisabled}
                            title={controlsDisabled ? '워밍업 녹화 중에는 조작이 잠깐 비활성화됩니다' : ''}
                        >
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
