
import { useEffect, useRef, useState } from "react";
import { FaceLandmarker, HandLandmarker, FilesetResolver, DrawingUtils } from "@mediapipe/tasks-vision";
import "./FaceDetector.css";

const FaceDetector = ({ onDistraction }) => {
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    // AI Models
    const [faceLandmarker, setFaceLandmarker] = useState(null);
    const [handLandmarker, setHandLandmarker] = useState(null);

    // State
    const [webcamRunning, setWebcamRunning] = useState(false);
    const [inputText, setInputText] = useState("");
    const [isDistracted, setIsDistracted] = useState(false);
    const [distractionReason, setDistractionReason] = useState("");

    // Refs for loop control
    const requestRef = useRef(null);
    const runningRef = useRef(false);
    const lastVideoTimeRef = useRef(-1);

    // Refs for Time-Based Distraction Logic
    const distractionStartTimeRef = useRef(null);

    const runningMode = "VIDEO";

    // Initialize Landmarkers
    useEffect(() => {
        const createLandmarkers = async () => {
            const filesetResolver = await FilesetResolver.forVisionTasks(
                "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.3/wasm"
            );

            // 1. Face Landmarker
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

            // 2. Hand Landmarker
            const handLandmarker = await HandLandmarker.createFromOptions(filesetResolver, {
                baseOptions: {
                    modelAssetPath: `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`,
                    delegate: "GPU"
                },
                runningMode: runningMode,
                numHands: 1
            });
            setHandLandmarker(handLandmarker);
        };
        createLandmarkers();
    }, []);

    // Cleanup loop on unmount
    useEffect(() => {
        return () => {
            if (requestRef.current) {
                cancelAnimationFrame(requestRef.current);
            }
        };
    }, []);

    // Helper: Euclidean Distance
    const euclideanDist = (p1, p2) => {
        return Math.sqrt(Math.pow(p1.x - p2.x, 2) + Math.pow(p1.y - p2.y, 2));
    };

    // Helper: Calculate Eye Aspect Ratio (EAR)
    const calculateEAR = (landmarks) => {
        // Indices for Left Eye (MediaPipe 468 landmarks)
        // Horizontal: 33 (inner), 133 (outer)
        // Vertical: 160-144, 158-153
        const leftEyeIndices = [[33, 133], [160, 144], [158, 153]];

        // Indices for Right Eye
        // Horizontal: 362 (inner), 263 (outer)
        // Vertical: 385-380, 387-373
        const rightEyeIndices = [[362, 263], [385, 380], [387, 373]];

        const getEyeRatio = (indices) => {
            // Horizontal
            const hDist = euclideanDist(landmarks[indices[0][0]], landmarks[indices[0][1]]);
            // Vertical
            const vDist1 = euclideanDist(landmarks[indices[1][0]], landmarks[indices[1][1]]);
            const vDist2 = euclideanDist(landmarks[indices[2][0]], landmarks[indices[2][1]]);

            return (vDist1 + vDist2) / (2 * hDist);
        };

        const leftEAR = getEyeRatio(leftEyeIndices);
        const rightEAR = getEyeRatio(rightEyeIndices);

        return (leftEAR + rightEAR) / 2;
    };

    const predictWebcam = async () => {
        const video = videoRef.current;
        const canvas = canvasRef.current;

        if (!runningRef.current || !video || !canvas || !faceLandmarker || !handLandmarker) return;

        let startTimeMs = performance.now();
        if (video.videoWidth > 0 && video.videoHeight > 0 && video.currentTime !== lastVideoTimeRef.current) {
            lastVideoTimeRef.current = video.currentTime;

            // 1. Hand Detection
            const handResults = handLandmarker.detectForVideo(video, startTimeMs);
            const handsDetected = handResults.landmarks && handResults.landmarks.length > 0;

            // 2. Face Detection
            const faceResults = faceLandmarker.detectForVideo(video, startTimeMs);

            // Distraction Logic
            let potentialDistraction = false;
            let currentReason = "";

            // A. Hands (Trigger only if occupying > 1/3 of screen)
            if (handsDetected) {
                // Calculate Bounding Box Area
                let distinctHandArea = 0;
                // handResults.landmarks is an array of arrays (one for each hand)
                for (const hand of handResults.landmarks) {
                    let minX = 1, minY = 1, maxX = 0, maxY = 0;
                    for (const lm of hand) {
                        if (lm.x < minX) minX = lm.x;
                        if (lm.x > maxX) maxX = lm.x;
                        if (lm.y < minY) minY = lm.y;
                        if (lm.y > maxY) maxY = lm.y;
                    }
                    const width = maxX - minX;
                    const height = maxY - minY;
                    const area = width * height;

                    if (area > 0.33) { // 1/3 of screen
                        potentialDistraction = true;
                        currentReason = `Hand Detected (${Math.round(area * 100)}% Area)`;
                        break;
                    }
                }
            }

            // B. Face Logic
            if (faceResults.facialTransformationMatrixes && faceResults.facialTransformationMatrixes.length > 0) {
                const matrix = faceResults.facialTransformationMatrixes[0].data;
                const landmarks = faceResults.faceLandmarks[0];

                // B-1. Head Pose
                const r21 = matrix[6];
                const r22 = matrix[10];
                const pitchRad = Math.atan2(r21, r22);
                const pitchDeg = pitchRad * (180 / Math.PI);
                const yawDeg = Math.atan2(-matrix[2], matrix[0]) * (180 / Math.PI);

                // B-2. Drowsiness (EAR)
                const ear = calculateEAR(landmarks);
                // EAR Threshold: < 0.2 usually means eyes closed. 
                // Adjust if needed. 0.25 is safer for "drowsy".
                const earThreshold = 0.24;

                // Check Conditions (Higher Sensitivity)
                // Pitch > 15 (was 20)
                // Yaw > 30 (was 45)
                // EAR < 0.24 (Drowsy)

                if (Math.abs(pitchDeg) > 15) {
                    potentialDistraction = true;
                    currentReason = `Head Nodding (${Math.round(pitchDeg)}°)`;
                } else if (Math.abs(yawDeg) > 30) {
                    potentialDistraction = true;
                    currentReason = `Head Turning (${Math.round(yawDeg)}°)`;
                } else if (ear < earThreshold) {
                    potentialDistraction = true;
                    currentReason = `Drowsiness Detected (Eyes Closed)`;
                }
            }

            // Time-Based Trigger Logic (1.5s Duration)
            if (potentialDistraction) {
                if (distractionStartTimeRef.current === null) {
                    distractionStartTimeRef.current = Date.now();
                } else {
                    const elapsed = Date.now() - distractionStartTimeRef.current;
                    // Lower duration threshold: 0.75 seconds (750ms)
                    if (elapsed > 750) {
                        setIsDistracted(true);
                        setDistractionReason(currentReason);
                    }
                }
            } else {
                distractionStartTimeRef.current = null;
            }

            // Draw Webcam Feed (Landmarks)
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

    // Camera Toggle
    const enableCam = () => {
        if (!faceLandmarker || !handLandmarker) {
            console.log("Wait! models not loaded yet.");
            return;
        }

        if (webcamRunning) {
            setWebcamRunning(false);
            runningRef.current = false;
            setIsDistracted(false);
            distractionStartTimeRef.current = null;

            if (requestRef.current) {
                cancelAnimationFrame(requestRef.current);
                requestRef.current = null;
            }
            if (videoRef.current && videoRef.current.srcObject) {
                const tracks = videoRef.current.srcObject.getTracks();
                tracks.forEach(track => track.stop());
                videoRef.current.srcObject = null;
            }
        } else {
            setWebcamRunning(true);
            runningRef.current = true;
            setIsDistracted(false);
            distractionStartTimeRef.current = null;

            const constraints = { video: true };
            navigator.mediaDevices.getUserMedia(constraints).then((stream) => {
                videoRef.current.srcObject = stream;
                videoRef.current.addEventListener("loadeddata", predictWebcam);
            });
        }
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
                {/* 1. Webcam Video */}
                <video
                    ref={videoRef}
                    style={{
                        width: "100%", height: "100%",
                        display: isDistracted ? "none" : "block",
                        transform: "scaleX(-1)"
                    }}
                    autoPlay
                    playsInline
                />

                {/* 2. Canvas for Landmarks (Webcam Overlay) */}
                <canvas
                    ref={canvasRef}
                    width="640"
                    height="480"
                    style={{
                        position: "absolute", left: 0, top: 0,
                        display: isDistracted ? "none" : "block",
                        transform: "scaleX(-1)"
                    }}
                />

                {/* 3. Fake Video Overlay */}
                <video
                    src="/fake_sample.mp4"
                    loop
                    autoPlay
                    muted
                    style={{
                        position: "absolute", left: 0, top: 0, width: "100%", height: "100%",
                        objectFit: "cover",
                        display: isDistracted ? "block" : "none",
                        zIndex: 10
                    }}
                />

                {/* Debug Alert */}
                {isDistracted && (
                    <div style={{
                        position: "absolute", top: "10px", right: "10px",
                        backgroundColor: "rgba(255, 0, 0, 0.7)", color: "white",
                        padding: "5px 10px", borderRadius: "5px", fontWeight: "bold",
                        zIndex: 20
                    }}>
                        DISTRACTED: {distractionReason}
                    </div>
                )}
            </div>

            <div className="controls">
                <button onClick={enableCam}>
                    {webcamRunning ? "Stop Camera" : "Start Camera"}
                </button>
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
