import { useState, useEffect, useCallback } from "react";
import { Clock, RefreshCw, Loader2, Mic, MonitorSmartphone, Bot } from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const MOOD_COLORS = {
  calm: "#E6E6FA",
  happy: "#FFD700",
  stressed: "#4A90D9",
  anxious: "#7B68EE",
  frustrated: "#48D1CC",
  sad: "#FF8C00",
  energetic: "#00FF7F",
  tired: "#FF8C00",
  neutral: "#94A3B8",
};

const SOURCE_ICONS = {
  voice: Mic,
  behavior: MonitorSmartphone,
  system: Bot,
  unknown: Bot,
};

export default function MoodHistory() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [userId] = useState("default");

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `${API_BASE}/orchestrate/history/${userId}?limit=100`
      );
      if (!res.ok) {
        throw new Error(`${res.status} ${res.statusText}`);
      }
      const data = await res.json();
      setHistory(data.entries || []);
    } catch (err) {
      setError(`Failed to load history: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchHistory();
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchHistory, 30000);
    return () => clearInterval(interval);
  }, [fetchHistory]);

  const formatTime = (isoString) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  const formatDate = (isoString) => {
    const date = new Date(isoString);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === today.toDateString()) return "Today";
    if (date.toDateString() === yesterday.toDateString()) return "Yesterday";
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  };

  // Group entries by date
  const grouped = history.reduce((acc, entry) => {
    const dateKey = formatDate(entry.timestamp);
    if (!acc[dateKey]) acc[dateKey] = [];
    acc[dateKey].push(entry);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Mood History</h2>
          <p className="text-gray-400 text-sm">
            Timeline of detected moods and environment adjustments
          </p>
        </div>
        <button
          onClick={fetchHistory}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm transition-colors disabled:opacity-50"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-xl px-5 py-3">
          <p className="text-sm text-red-400">⚠️ {error}</p>
        </div>
      )}

      {!loading && history.length === 0 && !error && (
        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-12 text-center">
          <p className="text-gray-500 text-sm">
            No mood history yet. Speak to Alexa or interact with the dashboard to
            start building your timeline.
          </p>
        </div>
      )}

      {Object.entries(grouped).map(([dateLabel, entries]) => (
        <div key={dateLabel}>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">
            {dateLabel}
          </h3>
          <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
            <div className="divide-y divide-gray-800">
              {entries.map((entry, i) => {
                const SourceIcon = SOURCE_ICONS[entry.source] || Bot;
                return (
                  <div
                    key={entry.entry_id || i}
                    className="p-4 flex items-center gap-4 hover:bg-gray-800/50 transition-colors"
                  >
                    <div className="flex items-center gap-2 w-20 shrink-0">
                      <Clock className="w-3 h-3 text-gray-500" />
                      <span className="text-sm text-gray-400">
                        {formatTime(entry.timestamp)}
                      </span>
                    </div>

                    <div
                      className="w-3 h-3 rounded-full shrink-0"
                      style={{
                        backgroundColor: MOOD_COLORS[entry.mood] || "#94A3B8",
                      }}
                    />

                    <div className="flex-1 min-w-0">
                      <span className="text-sm text-white capitalize font-medium">
                        {entry.mood}
                      </span>
                      <span className="text-gray-600 mx-2">·</span>
                      <span className="text-xs text-gray-400 capitalize">
                        {entry.cognitive_load} load
                      </span>
                      {entry.confidence > 0 && (
                        <>
                          <span className="text-gray-600 mx-2">·</span>
                          <span className="text-xs text-gray-500">
                            {Math.round(entry.confidence * 100)}%
                          </span>
                        </>
                      )}
                    </div>

                    <div className="flex items-center gap-2 max-w-xs shrink-0">
                      <SourceIcon className="w-3 h-3 text-gray-500 shrink-0" />
                      <p className="text-xs text-gray-500 truncate">
                        {entry.trigger}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
