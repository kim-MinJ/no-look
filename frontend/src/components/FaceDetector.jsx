import { useEffect, useRef, useState } from "react";
import { FaceLandmarker, FilesetResolver, DrawingUtils } from "@mediapipe/tasks-vision";
import "./FaceDetector.css";

const FaceDetector = ({ onDistraction }) => {
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const [landmarker, setLandmarker] = useState(null);
    const [webcamRunning, setWebcamRunning] = useState(false);
    const [inputText, setInputText] = useState("");

    // Refs for loop control to avoid closure staleness issues
    const requestRef = useRef(null);
    const runningRef = useRef(false);

    const runningMode = "VIDEO";

    // Initialize Landmarker
    useEffect(() => {
        const createLandmarker = async () => {
            const filesetResolver = await FilesetResolver.forVisionTasks(
                "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.3/wasm"
            );
            const newLandmarker = await FaceLandmarker.createFromOptions(filesetResolver, {
                baseOptions: {
                    modelAssetPath: `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`,
                    delegate: "GPU",
                },
                outputFaceBlendshapes: true,
                runningMode: runningMode,
                numFaces: 1,
            });
            setLandmarker(newLandmarker);
        };
        createLandmarker();
    }, []);

    // Cleanup loop on unmount
    useEffect(() => {
        return () => {
            if (requestRef.current) {
                cancelAnimationFrame(requestRef.current);
            }
        };
    }, []);

    const predictWebcam = async () => {
        const video = videoRef.current;
        const canvas = canvasRef.current;

        // Use runningRef.current to check status inside the loop
        if (!runningRef.current || !video || !canvas || !landmarker) return;

        let startTimeMs = performance.now();

        if (landmarker.detectForVideo) {
            if (video.videoWidth > 0 && video.videoHeight > 0) {
                const results = landmarker.detectForVideo(video, startTimeMs);

                const ctx = canvas.getContext("2d");
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                const drawingUtils = new DrawingUtils(ctx);

                if (results.faceLandmarks) {
                    for (const landmarks of results.faceLandmarks) {
                        drawingUtils.drawConnectors(
                            landmarks,
                            FaceLandmarker.FACE_LANDMARKS_TESSELATION,
                            { color: "#C0C0C070", lineWidth: 1 }
                        );
                        drawingUtils.drawConnectors(
                            landmarks,
                            FaceLandmarker.FACE_LANDMARKS_RIGHT_EYE,
                            { color: "#FF3030" }
                        );
                        drawingUtils.drawConnectors(
                            landmarks,
                            FaceLandmarker.FACE_LANDMARKS_LEFT_EYE,
                            { color: "#30FF30" }
                        );
                        drawingUtils.drawConnectors(
                            landmarks,
                            FaceLandmarker.FACE_LANDMARKS_FACE_OVAL,
                            { color: "#E0E0E0" }
                        );
                    }
                    // Distraction logic can be added here
                }
            }
        }

        // Schedule next frame if still running
        if (runningRef.current) {
            requestRef.current = requestAnimationFrame(predictWebcam);
        }
    };

    // Enable/Disable Webcam
    const enableCam = () => {
        if (!landmarker) {
            console.log("Wait! landmarker not loaded yet.");
            return;
        }

        if (webcamRunning) {
            // STOP
            setWebcamRunning(false);
            runningRef.current = false;

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
            // START
            setWebcamRunning(true);
            runningRef.current = true;

            const constraints = { video: true };
            navigator.mediaDevices.getUserMedia(constraints).then((stream) => {
                videoRef.current.srcObject = stream;
                // Add event listener only once implies we need to be careful not to stack them, 
                // but since we stop stream, it clears. 
                // However, requestAnimationFrame loop is self-sustaining.
                videoRef.current.addEventListener("loadeddata", predictWebcam);
            });
        }
    };

    const sendMacro = async (app) => {
        try {
            const response = await fetch("http://localhost:8000/control/macro", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: inputText, app: app })
            });
            const data = await response.json();
            console.log("Macro response:", data);
        } catch (err) {
            console.error("Macro failed:", err);
        }
    };

    return (
        <div className="face-detector">
            <div style={{ position: "relative" }}>
                <video
                    ref={videoRef}
                    style={{ width: "640px", height: "480px" }}
                    autoPlay
                    playsInline
                />
                <canvas
                    ref={canvasRef}
                    width="640"
                    height="480"
                    style={{ position: "absolute", left: 0, top: 0 }}
                />
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
