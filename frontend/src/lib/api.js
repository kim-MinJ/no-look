/**
 * API client for backend communication
 */

const API_BASE_URL = 'http://127.0.0.1:8000';

/**
 * Request AI reply candidates
 * @param {string} transcript - Input transcript text
 * @param {string} tone - Reply tone: 'short', 'polite', or 'casual'
 * @param {boolean} useMock - If true, return mock response
 * @returns {Promise<{candidates: string[]}>} Response with candidates
 */
export async function requestAiReply(transcript, tone = 'polite', useMock = true) {
    if (useMock) {
        return getMockAiReply(transcript, tone);
    }

    try {
        const response = await fetch(`${API_BASE_URL}/ai/reply`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ transcript, tone })
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('AI Reply API failed, using mock:', error);
        return getMockAiReply(transcript, tone);
    }
}

/**
 * Request macro to type text
 * @param {string} text - Text to type
 * @param {boolean} useMock - If true, return mock response
 * @returns {Promise<{success: boolean, message: string}>}
 */
export async function requestMacroType(text, useMock = true) {
    if (useMock) {
        return getMockMacroResponse();
    }

    try {
        const response = await fetch(`${API_BASE_URL}/macro/type`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ text })
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        return { success: true, message: '채팅 입력 완료' };
    } catch (error) {
        console.error('Macro API failed:', error);
        return { success: false, message: '매크로 실행 실패' };
    }
}

/**
 * Generate mock AI reply
 */
function getMockAiReply(transcript, tone) {
    const shortReplies = [
        '네, 알겠습니다.',
        '확인했습니다.',
        '동의합니다.'
    ];

    const politeReplies = [
        '말씀하신 내용 잘 이해했습니다. 검토 후 답변 드리겠습니다.',
        '좋은 의견 감사합니다. 해당 방향으로 진행하겠습니다.',
        '네, 그 부분에 대해서는 추가 논의가 필요할 것 같습니다.'
    ];

    const casualReplies = [
        '아 그렇군요! 좋은 생각이네요.',
        '음, 그 방법도 괜찮을 것 같아요.',
        '오 그거 재밌는 아이디어네요!'
    ];

    const replies = {
        short: shortReplies,
        polite: politeReplies,
        casual: casualReplies
    };

    // Simulate API delay
    return new Promise((resolve) => {
        setTimeout(() => {
            resolve({
                candidates: replies[tone] || politeReplies
            });
        }, 500);
    });
}

/**
 * Generate mock macro response
 */
function getMockMacroResponse() {
    return new Promise((resolve) => {
        setTimeout(() => {
            // 80% success rate
            if (Math.random() > 0.2) {
                resolve({ success: true, message: '채팅 입력 완료 (Mock)' });
            } else {
                resolve({ success: false, message: '매크로 실행 실패 (Mock)' });
            }
        }, 300);
    });
}
