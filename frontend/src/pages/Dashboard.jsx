import { useState, useEffect, useRef } from "react";
import { Brain, Activity, Lightbulb, Mic, MicOff, MonitorSmartphone } from "lucide-react";
import MoodIndicator from "../components/MoodIndicator";
import CognitiveLoadMeter from "../components/CognitiveLoadMeter";
import EnvironmentPanel from "../components/EnvironmentPanel";
import VoiceInput from "../components/VoiceInput";
import BehaviorTracker from "../components/BehaviorTracker";
import AlexaNotification from "../components/patterns/AlexaNotification";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000/alexa/stream";

export default function Dashboard() {
  const [mood, setMood] = useState("neutral");
  const [cognitiveLoad, setCognitiveLoad] = useState("moderate");
  const [confidence, setConfidence] = useState(0);
  const [environment, setEnvironment] = useState(null);
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [behaviorLog, setBehaviorLog] = useState([]);
  const [alexaResponse, setAlexaResponse] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [llmPowered, setLlmPowered] = useState(false);
  const [alexaNotifications, setAlexaNotifications] = useState([]);
  const wsRef = useRef(null);
  const lastEnvChangeRef = useRef(0); // Cooldown timer for behavior LLM calls

  // WebSocket connection for real-time updates
  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        setTimeout(connect, 3000);
      };
      ws.onerror = () => setConnected(false);

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "mood_update") {
          setMood(data.mood);
          setCognitiveLoad(data.cognitive_load);
          setConfidence(data.confidence);
          setEnvironment(data.environment);
          setLastUpdate(new Date());
        } else if (data.type === "environment_update") {
          setCognitiveLoad(data.cognitive_load);
          setEnvironment(data.environment);
          setLastUpdate(new Date());
        }
      };
    };

    connect();
    return () => wsRef.current?.close();
  }, []);

  // Handle mood result (from voice or text)
  const handleMoodResult = async (moodData) => {
    // Immediately update panels with mood service result (this is authoritative)
    setMood(moodData.mood);
    setCognitiveLoad(moodData.cognitive_load);
    setConfidence(moodData.confidence);
    setError("");

    // Get the transcript (from voice) or original text (from text input)
    const speechText =
      moodData.speech_features?.transcript ||
      moodData._originalText ||
      null;

    // Send to orchestrator — LLM decides environment actions
    try {
      const hour = new Date().getHours();
      const timeOfDay =
        hour < 6 ? "late night" :
        hour < 12 ? "morning" :
        hour < 17 ? "afternoon" :
        hour < 21 ? "evening" : "night";

      const res = await fetch(`${API_BASE}/orchestrate/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          speech_text: speechText,
          behavior_signals: [],
          room_id: "living-room",
          time_of_day: timeOfDay,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setEnvironment(data.actions);
        setAlexaResponse(data.alexa_response);
        setReasoning(data.reasoning);
        setLlmPowered(data.llm_powered);
        // Fire the voice notification
        if (data.alexa_response) {
          setAlexaNotifications([{
            id: Date.now(),
            text: data.alexa_response,
            explanation: data.reasoning || "",
            llmPowered: data.llm_powered,
            tone: data.mood === "stressed" || data.mood === "frustrated" || data.mood === "anxious" ? "alert" : "calm",
          }]);
        }
        // DON'T override mood/cognitive_load — the mood service result is canonical
      }
    } catch (err) {
      // Fallback: use the preset-based device adjust
      try {
        const envRes = await fetch(`${API_BASE}/devices/adjust`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mood: moodData.mood,
            cognitive_load: moodData.cognitive_load,
          }),
        });
        if (envRes.ok) {
          const envData = await envRes.json();
          setEnvironment(envData.environment);
        }
      } catch {}
    }
    setLastUpdate(new Date());
  };

  // Handle behavior signal results — calls LLM every 30s with current state
  const handleBehaviorResult = async (result) => {
    setCognitiveLoad(result.cognitive_load);
    setBehaviorLog((prev) => [
      { ...result, timestamp: new Date() },
      ...prev.slice(0, 19),
    ]);

    // Call LLM every 30 seconds (regardless of state change)
    const now = Date.now();
    if (now - lastEnvChangeRef.current < 30000) return;
    lastEnvChangeRef.current = now;

    // Always send current state to orchestrator for environment adjustment
    try {
      const hour = new Date().getHours();
      const timeOfDay =
        hour < 6 ? "late night" :
        hour < 12 ? "morning" :
        hour < 17 ? "afternoon" :
        hour < 21 ? "evening" : "night";

      const res = await fetch(`${API_BASE}/orchestrate/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          behavior_signals: result._rawSignals || [],
          room_id: "living-room",
          time_of_day: timeOfDay,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setEnvironment(data.actions);
        if (data.alexa_response) setAlexaResponse(data.alexa_response);
        if (data.reasoning) setReasoning(data.reasoning);
        setLlmPowered(data.llm_powered);
        // Fire the voice notification
        if (data.alexa_response) {
          setAlexaNotifications([{
            id: Date.now(),
            text: data.alexa_response,
            explanation: data.reasoning || "",
            llmPowered: data.llm_powered,
            tone: "calm",
          }]);
        }
      }
    } catch (err) {
      console.error("Orchestrator failed:", err);
    }

    setLastUpdate(new Date());
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Mood Dashboard</h2>
          <p className="text-gray-400 text-sm">
            Real-time mood & cognitive load monitoring via voice and behavior
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${
              connected ? "bg-green-400" : "bg-red-400"
            }`}
          />
          <span className="text-xs text-gray-500">
            {connected ? "Live" : "Offline"}
          </span>
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="flex items-center gap-2 mb-4">
            <Brain className="w-5 h-5 text-indigo-400" />
            <h3 className="font-semibold text-white">Current Mood</h3>
          </div>
          <MoodIndicator mood={mood} confidence={confidence} />
        </div>

        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="w-5 h-5 text-amber-400" />
            <h3 className="font-semibold text-white">Cognitive Load</h3>
          </div>
          <CognitiveLoadMeter level={cognitiveLoad} />
        </div>

        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="flex items-center gap-2 mb-4">
            <Lightbulb className="w-5 h-5 text-yellow-400" />
            <h3 className="font-semibold text-white">Environment</h3>
          </div>
          <EnvironmentPanel environment={environment} />
        </div>
      </div>

      {/* Voice Input — The primary interaction method */}
      <VoiceInput
        apiBase={API_BASE}
        onMoodResult={handleMoodResult}
        onError={setError}
      />

      {/* Behavior Tracker — Monitors user interactions */}
      <BehaviorTracker
        apiBase={API_BASE}
        onBehaviorResult={handleBehaviorResult}
        behaviorLog={behaviorLog}
      />

      {/* Alexa Response & LLM Reasoning */}
      {alexaResponse && (
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-lg">🔊</span>
            <h3 className="font-semibold text-white">Alexa Says</h3>
            {llmPowered && (
              <span className="text-xs bg-indigo-900/40 text-indigo-300 px-2 py-0.5 rounded-full ml-auto">
                LLM-Powered
              </span>
            )}
          </div>
          <p className="text-gray-200 italic">"{alexaResponse}"</p>
          {reasoning && (
            <div className="mt-3 pt-3 border-t border-gray-800">
              <p className="text-xs text-gray-500">
                <span className="text-gray-400 font-medium">AI Reasoning:</span>{" "}
                {reasoning}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-xl px-5 py-3">
          <p className="text-sm text-red-400">⚠️ {error}</p>
        </div>
      )}

      {/* Last update */}
      {lastUpdate && (
        <p className="text-xs text-gray-600 text-center">
          Last update: {lastUpdate.toLocaleTimeString()}
        </p>
      )}

      {/* Alexa voice notification popup with TTS */}
      <AlexaNotification
        notifications={alexaNotifications}
        onDismiss={(id) => setAlexaNotifications((prev) => prev.filter((n) => n.id !== id))}
        onDismissAll={() => setAlexaNotifications([])}
      />
    </div>
  );
}
