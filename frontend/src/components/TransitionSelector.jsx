import { useState } from 'react';
import { setTransitionEffect } from '../lib/api';

export default function TransitionSelector({ addToast }) {
    const [effect, setEffect] = useState('natural_lag');

    const handleApply = async () => {
        try {
            const res = await setTransitionEffect(effect);
            if (res.ok) {
                addToast(`전환 효과가 '${effect}'(으)로 변경되었습니다`, 'success');
            } else {
                addToast('전환 효과 변경 실패', 'error');
            }
        } catch (e) {
            console.error(e);
            addToast('서버 통신 오류', 'error');
        }
    };

    return (
        <div className="transition-selector-card">
            <div className="selector-title">전환 효과 설정</div>
            <div className="selector-row">
                <select
                    className="selector-input"
                    value={effect}
                    onChange={(e) => setEffect(e.target.value)}
                >
                    <option value="natural_lag">Natural Lag (자연스러운 랙/멈춤)</option>
                    <option value="blackout">Blackout (암전 to 페이드인)</option>
                    <option value="falling">Falling (떨어짐 효과)</option>

                </select>
                <button className="btn btn-primary btn-apply" onClick={handleApply}>
                    적용
                </button>
            </div>
        </div>
    );
}
