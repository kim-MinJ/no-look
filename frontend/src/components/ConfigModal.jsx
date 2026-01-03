import { useState, useEffect } from 'react';
import { getConfig, saveConfig } from '../lib/api';
import './ConfigModal.css';

export default function ConfigModal({ isOpen, onClose, onSave }) {
    const [config, setConfig] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    // 태그 입력용 임시 상태
    const [keywordInput, setKeywordInput] = useState('');
    const [patternInput, setPatternInput] = useState('');

    useEffect(() => {
        if (isOpen) {
            loadConfig();
        }
    }, [isOpen]);

    const loadConfig = async () => {
        try {
            setLoading(true);
            const data = await getConfig();
            setConfig(data);
        } catch (err) {
            console.error('설정 불러오기 실패:', err);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        try {
            setSaving(true);
            await saveConfig(config);
            onSave?.();
            onClose();
        } catch (err) {
            console.error('설정 저장 실패:', err);
            alert('설정 저장에 실패했습니다: ' + err.message);
        } finally {
            setSaving(false);
        }
    };

    // 키워드 추가/삭제
    const addKeyword = () => {
        if (!keywordInput.trim()) return;
        setConfig(prev => ({
            ...prev,
            triggers: {
                ...prev.triggers,
                keywords: [...prev.triggers.keywords, keywordInput.trim()]
            }
        }));
        setKeywordInput('');
    };

    const removeKeyword = (index) => {
        setConfig(prev => ({
            ...prev,
            triggers: {
                ...prev.triggers,
                keywords: prev.triggers.keywords.filter((_, i) => i !== index)
            }
        }));
    };

    // 패턴 추가/삭제
    const addPattern = () => {
        if (!patternInput.trim()) return;
        setConfig(prev => ({
            ...prev,
            triggers: {
                ...prev.triggers,
                question_patterns: [...prev.triggers.question_patterns, patternInput.trim()]
            }
        }));
        setPatternInput('');
    };

    const removePattern = (index) => {
        setConfig(prev => ({
            ...prev,
            triggers: {
                ...prev.triggers,
                question_patterns: prev.triggers.question_patterns.filter((_, i) => i !== index)
            }
        }));
    };

    if (!isOpen) return null;

    return (
        <div className="config-modal-overlay" onClick={onClose}>
            <div className="config-modal-content" onClick={(e) => e.stopPropagation()}>
                <div className="config-modal-header">
                    <h2>🔧 AI 비서 설정</h2>
                    <button className="close-btn" onClick={onClose}>✕</button>
                </div>

                {loading ? (
                    <div className="config-loading">설정을 불러오는 중...</div>
                ) : config ? (
                    <div className="config-modal-body">
                        {/* 트리거 설정 */}
                        <div className="config-section">
                            <h3>🎯 트리거 설정</h3>

                            <label>키워드 (이름, 반응할 단어)</label>
                            <div className="tag-container">
                                {config.triggers.keywords.map((kw, i) => (
                                    <span key={i} className="tag-item">
                                        {kw}
                                        <button onClick={() => removeKeyword(i)}>×</button>
                                    </span>
                                ))}
                            </div>
                            <div className="tag-input-box">
                                <input
                                    type="text"
                                    value={keywordInput}
                                    onChange={(e) => setKeywordInput(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && addKeyword()}
                                    placeholder="키워드 입력 후 Enter"
                                />
                                <button onClick={addKeyword}>+</button>
                            </div>

                            <label>질문 패턴</label>
                            <div className="tag-container">
                                {config.triggers.question_patterns.map((pat, i) => (
                                    <span key={i} className="tag-item">
                                        {pat}
                                        <button onClick={() => removePattern(i)}>×</button>
                                    </span>
                                ))}
                            </div>
                            <div className="tag-input-box">
                                <input
                                    type="text"
                                    value={patternInput}
                                    onChange={(e) => setPatternInput(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && addPattern()}
                                    placeholder="패턴 입력 후 Enter"
                                />
                                <button onClick={addPattern}>+</button>
                            </div>
                        </div>

                        {/* 페르소나 설정 */}
                        <div className="config-section">
                            <h3>🎭 페르소나 설정</h3>
                            <label>역할</label>
                            <input
                                type="text"
                                value={config.personalization.user_role}
                                onChange={(e) => setConfig(prev => ({
                                    ...prev,
                                    personalization: { ...prev.personalization, user_role: e.target.value }
                                }))}
                            />

                            <label>회의/강의 주제</label>
                            <input
                                type="text"
                                value={config.personalization.meeting_topic}
                                onChange={(e) => setConfig(prev => ({
                                    ...prev,
                                    personalization: { ...prev.personalization, meeting_topic: e.target.value }
                                }))}
                            />

                            <label>말투</label>
                            <input
                                type="text"
                                value={config.personalization.speaking_style}
                                onChange={(e) => setConfig(prev => ({
                                    ...prev,
                                    personalization: { ...prev.personalization, speaking_style: e.target.value }
                                }))}
                            />
                        </div>

                        {/* 시스템 설정 */}
                        <div className="config-section">
                            <h3>⚙️ 시스템 설정</h3>
                            <label>마이크 인덱스</label>
                            <input
                                type="number"
                                value={config.settings.device_index}
                                onChange={(e) => setConfig(prev => ({
                                    ...prev,
                                    settings: { ...prev.settings, device_index: parseInt(e.target.value) }
                                }))}
                            />

                            <label>모델 크기</label>
                            <select
                                value={config.settings.model_size}
                                onChange={(e) => setConfig(prev => ({
                                    ...prev,
                                    settings: { ...prev.settings, model_size: e.target.value }
                                }))}
                            >
                                <option value="tiny">Tiny (빠름, 낮은 정확도)</option>
                                <option value="base">Base</option>
                                <option value="small">Small</option>
                                <option value="medium">Medium (권장)</option>
                                <option value="large">Large (느림, 높은 정확도)</option>
                            </select>

                            <label>샘플 레이트 (Hz)</label>
                            <select
                                value={config.settings.sample_rate}
                                onChange={(e) => setConfig(prev => ({
                                    ...prev,
                                    settings: { ...prev.settings, sample_rate: parseInt(e.target.value) }
                                }))}
                            >
                                <option value="16000">16000</option>
                                <option value="44100">44100</option>
                                <option value="48000">48000 (권장)</option>
                            </select>
                        </div>
                    </div>
                ) : (
                    <div className="config-error">설정을 불러올 수 없습니다.</div>
                )}

                <div className="config-modal-footer">
                    <button className="btn-cancel" onClick={onClose}>취소</button>
                    <button
                        className="btn-save"
                        onClick={handleSave}
                        disabled={saving || loading}
                    >
                        {saving ? '저장 중...' : '저장'}
                    </button>
                </div>
            </div>
        </div>
    );
}
