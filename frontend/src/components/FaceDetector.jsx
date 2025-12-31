import { useEffect, useRef, useState } from "react";
import { FaceLandmarker, HandLandmarker, FilesetResolver, DrawingUtils } from "@mediapipe/tasks-vision";
import OBSWebSocket from "obs-websocket-js";
import "./FaceDetector.css";

const FaceDetector = ({ onDistraction }) => {
    const videoRef = useRef(null);
    const canvasRef = useRef(null);

    // AI Models (MediaPipe)
    const [faceLandmarker, setFaceLandmarker] = useState(null);
    const [handLandmarker, setHandLandmarker] = useState(null);

    // State
    const [webcamRunning, setWebcamRunning] = useState(false);
    const [inputText, setInputText] = useState("");

    // Distraction State
    const [isDistracted, setIsDistracted] = useState(false);
    const [distractionReason, setDistractionReason] = useState("");
    const [botReaction, setBotReaction] = useState(null);

    // OBS State
    const obsRef = useRef(new OBSWebSocket());
    const [obsConnected, setObsConnected] = useState(false);

    // AI Backend WebSocket
    const aiWsRef = useRef(null);
    const [aiConnected, setAiConnected] = useState(false);

    // Refs for loop control
    const requestRef = useRef(null);
    const runningRef = useRef(false);
    const lastVideoTimeRef = useRef(-1);
    const distractionStartTimeRef = useRef(null);

    const runningMode = "VIDEO";

    // 1. Initialize OBS & Models & AI
    useEffect(() => {
        connectOBS();
        connectAI();

        const createLandmarkers = async () => {
            console.log("🔄 Loading MediaPipe models...");
            const filesetResolver = await FilesetResolver.forVisionTasks(
                "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.3/wasm"
            );

            const faceLandmarker = await FaceLandmarker.createFromOptions(filesetResolver, {
                baseOptions: {
                    modelAssetPath: `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`,
                    delegate: "GPU",
                },
                outputFaceBlendshapes: true,
                outputFacialTransformationMatrixes: true,
                runningMode: runningMode,
                numFaces: 1,
            });
            setFaceLandmarker(faceLandmarker);
            console.log("✅ FaceLandmarker loaded");

            const handLandmarker = await HandLandmarker.createFromOptions(filesetResolver, {
                baseOptions: {
                    modelAssetPath: `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`,
                    delegate: "GPU"
                },
                runningMode: runningMode,
                numHands: 1
            });
            setHandLandmarker(handLandmarker);
            console.log("✅ HandLandmarker loaded");
            console.log("✅ All MediaPipe models ready!");
        };
        createLandmarkers();

        return () => {
            if (obsConnected) obsRef.current.disconnect();
            if (aiWsRef.current) aiWsRef.current.close();
        };
    }, []);

    // 2. OBS Connection
    const connectOBS = async () => {
        try {
            await obsRef.current.connect("ws://localhost:4455", "CDeP1CouhTyM5FTT");
            console.log("✅ OBS Connected");
            setObsConnected(true);
        } catch (error) {
            console.error("❌ OBS Connection Failed", error);
        }
    };

    const switchOBSScene = async (sceneName) => {
        if (!obsRef.current || !obsConnected) return;
        try {
            await obsRef.current.call("SetCurrentProgramScene", { sceneName });
            console.log(`🎬 OBS Scene: ${sceneName}`);
        } catch (e) {
            console.warn("⚠️ OBS Switch Failed:", e);
        }
    };

    // 3. AI Backend WebSocket
    const connectAI = () => {
        const ws = new WebSocket("ws://localhost:8000/ws/ai");

        ws.onopen = () => {
            console.log("✅ AI Backend Connected");
            setAiConnected(true);
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === "reaction") {
                setBotReaction(data.text);
                console.log(`🤖 Bot: ${data.text}`);
                setTimeout(() => setBotReaction(null), 5000);
            }
        };

        ws.onerror = (error) => {
            console.error("❌ AI Backend Error:", error);
            setAiConnected(false);
        };

        ws.onclose = () => {
            console.log("❌ AI Backend Disconnected");
            setAiConnected(false);
            setTimeout(connectAI, 3000);
        };

        aiWsRef.current = ws;
    };

    // 4. Request AI reaction when distracted
    useEffect(() => {
        if (isDistracted && aiWsRef.current && aiWsRef.current.readyState === WebSocket.OPEN) {
            aiWsRef.current.send(JSON.stringify({
                type: "reaction_request",
                isDistracted: true
            }));
        }
    }, [isDistracted]);

    // 5. Effect: Handle Distraction -> OBS Switch
    useEffect(() => {
        if (isDistracted) {
            console.log("🚨 Distracted! Switching to Fake");
            switchOBSScene("Fake");
        } else {
            console.log("✅ Safe! Switching to Real");
            switchOBSScene("Real");
        }
        if (onDistraction) onDistraction(isDistracted);
    }, [isDistracted]);

    // Cleanup loop
    useEffect(() => {
        return () => {
            if (requestRef.current) cancelAnimationFrame(requestRef.current);
        };
    }, []);

    // Helper: EAR
    const calculateEAR = (landmarks) => {
        const euclideanDist = (p1, p2) => Math.sqrt(Math.pow(p1.x - p2.x, 2) + Math.pow(p1.y - p2.y, 2));
        const leftEyeIndices = [[33, 133], [160, 144], [158, 153]];
        const rightEyeIndices = [[362, 263], [385, 380], [387, 373]];
        const getEyeRatio = (indices) => {
            const hDist = euclideanDist(landmarks[indices[0][0]], landmarks[indices[0][1]]);
            const vDist1 = euclideanDist(landmarks[indices[1][0]], landmarks[indices[1][1]]);
            const vDist2 = euclideanDist(landmarks[indices[2][0]], landmarks[indices[2][1]]);
            return (vDist1 + vDist2) / (2 * hDist);
        };
        return (getEyeRatio(leftEyeIndices) + getEyeRatio(rightEyeIndices)) / 2;
    };

    // 6. Main Prediction Loop
    const predictWebcam = async () => {
        const video = videoRef.current;
        const canvas = canvasRef.current;
        if (!runningRef.current || !video || !canvas || !faceLandmarker || !handLandmarker) return;

        let startTimeMs = performance.now();
        if (video.videoWidth > 0 && video.videoHeight > 0 && video.currentTime !== lastVideoTimeRef.current) {
            lastVideoTimeRef.current = video.currentTime;

            const handResults = handLandmarker.detectForVideo(video, startTimeMs);
            const handsDetected = handResults.landmarks && handResults.landmarks.length > 0;
            const faceResults = faceLandmarker.detectForVideo(video, startTimeMs);

            let potentialDistraction = false;
            let currentReason = "";

            // Logic: Hand Detection
            if (handsDetected && faceResults.faceLandmarks && faceResults.faceLandmarks.length > 0) {
                potentialDistraction = true;
                currentReason = "Hand Detected";
            }

            // Logic: Head Pose & Drowsiness
            if (faceResults.facialTransformationMatrixes && faceResults.facialTransformationMatrixes.length > 0) {
                const matrix = faceResults.facialTransformationMatrixes[0].data;
                const landmarks = faceResults.faceLandmarks[0];

                const r21 = matrix[6];
                const r22 = matrix[10];
                const pitchRad = Math.atan2(r21, r22);
                const pitchDeg = pitchRad * (180 / Math.PI);
                const yawDeg = Math.atan2(-matrix[2], matrix[0]) * (180 / Math.PI);
                const ear = calculateEAR(landmarks);

                if (Math.abs(pitchDeg) > 15) {
                    potentialDistraction = true;
                    currentReason = `Head Nodding (${Math.round(pitchDeg)}°)`;
                } else if (Math.abs(yawDeg) > 30) {
                    potentialDistraction = true;
                    currentReason = `Head Turning (${Math.round(yawDeg)}°)`;
                } else if (ear < 0.24) {
                    potentialDistraction = true;
                    currentReason = `Drowsiness`;
                }
            }

            // Time-based Trigger (750ms)
            if (potentialDistraction) {
                if (distractionStartTimeRef.current === null) {
                    distractionStartTimeRef.current = Date.now();
                } else if (Date.now() - distractionStartTimeRef.current > 750) {
                    setIsDistracted(true);
                    setDistractionReason(currentReason);
                }
            } else {
                distractionStartTimeRef.current = null;
                setIsDistracted(false);
            }

            // Draw
            const ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const drawingUtils = new DrawingUtils(ctx);
            if (faceResults.faceLandmarks) {
                for (const landmarks of faceResults.faceLandmarks) {
                    drawingUtils.drawConnectors(landmarks, FaceLandmarker.FACE_LANDMARKS_TESSELATION, { color: "#C0C0C070", lineWidth: 1 });
                }
            }
            if (handResults.landmarks) {
                for (const landmarks of handResults.landmarks) {
                    drawingUtils.drawConnectors(landmarks, HandLandmarker.HAND_CONNECTIONS, { color: "#FF0000", lineWidth: 2 });
                }
            }
        }

        if (runningRef.current) {
            requestRef.current = requestAnimationFrame(predictWebcam);
        }
    };

    // 7. Camera Toggle with DEBUG LOGS
    const enableCam = () => {
        console.log("🎥 ========== ENABLE CAM CALLED ==========");
        console.log("  faceLandmarker:", faceLandmarker ? "✅ Ready" : "❌ Not loaded");
        console.log("  handLandmarker:", handLandmarker ? "✅ Ready" : "❌ Not loaded");
        console.log("  webcamRunning:", webcamRunning);

        if (!faceLandmarker || !handLandmarker) {
            console.error("❌ MediaPipe models not loaded yet!");
            alert("Please wait for MediaPipe models to load...");
            return;
        }

        if (webcamRunning) {
            console.log("⏹️ Stopping camera...");
            setWebcamRunning(false);
            runningRef.current = false;
            setIsDistracted(false);
            if (requestRef.current) cancelAnimationFrame(requestRef.current);
            if (videoRef.current && videoRef.current.srcObject) {
                videoRef.current.srcObject.getTracks().forEach(t => t.stop());
                videoRef.current.srcObject = null;
            }
            console.log("✅ Camera stopped");
        } else {
            console.log("▶️ Starting camera...");
            setWebcamRunning(true);
            runningRef.current = true;
            setIsDistracted(false);

            const constraints = { video: true };
            console.log("📹 Requesting webcam with constraints:", constraints);

            navigator.mediaDevices.getUserMedia(constraints)
                .then((stream) => {
                    console.log("✅ SUCCESS! Webcam stream obtained");
                    console.log("  Stream ID:", stream.id);
                    console.log("  Video tracks:", stream.getVideoTracks().length);
                    stream.getVideoTracks().forEach((track, idx) => {
                        console.log(`    Track ${idx}:`, track.label, track.enabled ? "✅" : "❌");
                    });

                    if (videoRef.current) {
                        videoRef.current.srcObject = stream;
                        console.log("✅ Stream assigned to <video> element");
                        videoRef.current.addEventListener("loadeddata", () => {
                            console.log("✅ Video loadeddata event fired");
                            console.log("  Video size:", videoRef.current.videoWidth, "x", videoRef.current.videoHeight);
                            predictWebcam();
                        });
                    } else {
                        console.error("❌ videoRef.current is NULL!");
                    }
                })
                .catch((err) => {
                    console.error("❌ =================================");
                    console.error("❌ WEBCAM ACCESS FAILED!");
                    console.error("❌ Error name:", err.name);
                    console.error("❌ Error message:", err.message);
                    console.error("❌ =================================");

                    let userMessage = `Webcam Error: ${err.name}\n\n`;
                    if (err.name === "NotAllowedError") {
                        userMessage += "Camera permission denied!\n";
                        userMessage += "Please allow camera access in your browser settings.";
                    } else if (err.name === "NotFoundError") {
                        userMessage += "No camera device found!\n";
                        userMessage += "Please check if your webcam is connected.";
                    } else if (err.name === "NotReadableError") {
                        userMessage += "Camera is in use by another application!\n";
                        userMessage += "Please close other apps using the camera.";
                    } else {
                        userMessage += err.message;
                    }

                    alert(userMessage);
                    setWebcamRunning(false);
                    runningRef.current = false;
                });
        }
        console.log("==========================================");
    };

    const sendMacro = async (app) => {
        try {
            await fetch("http://localhost:8000/control/macro", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: inputText, app: app })
            });
        } catch (err) {
            console.error(err);
        }
    };

    return (
        <div className="face-detector">
            <div style={{ position: "relative", width: "640px", height: "480px" }}>
                <video
                    ref={videoRef}
                    style={{ width: "100%", height: "100%", transform: "scaleX(-1)" }}
                    autoPlay
                    playsInline
                />
                <canvas
                    ref={canvasRef}
                    width="640"
                    height="480"
                    style={{ position: "absolute", left: 0, top: 0, transform: "scaleX(-1)" }}
                />

                {isDistracted && (
                    <div style={{
                        position: "absolute", top: "10px", right: "10px",
                        backgroundColor: "rgba(255, 0, 0, 0.7)", color: "white",
                        padding: "5px 10px", borderRadius: "5px", fontWeight: "bold"
                    }}>
                        🚨 DISTRACTED: {distractionReason}
                    </div>
                )}

                {botReaction && (
                    <div style={{
                        position: "absolute", bottom: "10px", left: "10px",
                        backgroundColor: "rgba(0, 123, 255, 0.9)", color: "white",
                        padding: "8px 12px", borderRadius: "5px", maxWidth: "300px"
                    }}>
                        🤖 {botReaction}
                    </div>
                )}
            </div>

            <div className="controls">
                <button onClick={enableCam}>
                    {webcamRunning ? "Stop Camera" : "Start Camera"}
                </button>
                <div style={{ marginLeft: "10px", display: "inline-block", fontSize: "0.9em" }}>
                    OBS: {obsConnected ? "✅" : "❌"} | AI: {aiConnected ? "✅" : "❌"}
                </div>
                <div className="macro-control" style={{ marginTop: "10px" }}>
                    <input
                        type="text"
                        value={inputText}
                        onChange={(e) => setInputText(e.target.value)}
                        placeholder="Message to type..."
                    />
                    <button onClick={() => sendMacro('zoom')}>Send to Zoom</button>
                    <button onClick={() => sendMacro('discord')}>Send to Discord</button>
                </div>
            </div>
        </div>
    );
};

export default FaceDetector;
