import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const API = "http://127.0.0.1:8000";

// ─── Default cover text (30+ adjectives for ample capacity) ─────────────────
const DEFAULT_COVER = `The very bright morning sky stretched over an incredibly vast and ancient landscape. A really calm river wound through the quite narrow valley, carrying fresh mountain water past the old stone bridge. Tall green trees lined the gentle slopes on either side, their dense canopy casting cool shadow over the rough path below. A fairly strong wind swept across the open fields, bending the wild grass in slow and graceful waves. The distant mountains appeared sharp and clear against the pure white sky, their ancient peaks still covered in fresh snow. Every quiet village along the route had its own rich and delicate character, with colorful wooden shutters and clean cobblestone streets. It was an extremely peaceful and beautiful world, full of vivid and unusual detail.`;

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function apiPost(path, body) {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${path} → ${res.status}: ${txt}`);
  }
  return res.json();
}

// Sequential carrier-word highlighting.
// Iterates the rendered words and matches them against the ordered list of
// carrier adjectives returned by the encoder.
function renderHighlighted(text, carriers) {
  if (!text) return null;
  if (!carriers || carriers.length === 0) return <>{text}</>;

  // Tokenise preserving all whitespace/punctuation
  const tokens = text.split(/(\s+|[.,;:!?—–"'()\[\]{}])/);
  let ci = 0;

  return tokens.map((tok, i) => {
    const bare = tok.toLowerCase().replace(/[^a-z]/g, "");
    if (
      ci < carriers.length &&
      bare === carriers[ci].toLowerCase()
    ) {
      ci++;
      return (
        <mark key={i} className="carrier-word" title="carrier adjective">
          {tok}
        </mark>
      );
    }
    return <span key={i}>{tok}</span>;
  });
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionLabel({ children }) {
  return <div className="section-label">{children}</div>;
}

function Field({ label, children }) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      {children}
    </div>
  );
}

function CapacityBar({ slots, needed }) {
  const pct = slots === 0 ? 0 : Math.min(100, Math.round((slots / Math.max(needed, 1)) * 100));
  const over = needed > slots;
  return (
    <div className="capacity-bar-wrap">
      <div className="capacity-row">
        <span>Cover capacity</span>
        <span>
          {slots} slot{slots !== 1 ? "s" : ""} → ~{Math.floor(slots / 3)} char{Math.floor(slots / 3) !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="capacity-track">
        <div
          className={`capacity-fill${over ? " over" : ""}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {over && (
        <div className="capacity-warning">
          ⚑ Cover text needs ~{needed} slots but has {slots}. Add more adjectives.
        </div>
      )}
    </div>
  );
}

function MetricCard({ value, label, sub, barPct }) {
  return (
    <div className="metric-card">
      <div className="metric-number">{value ?? "—"}</div>
      <div className="metric-label">{label}</div>
      {sub && <div className="metric-sub">{sub}</div>}
      {barPct !== undefined && (
        <div className="trit-bar">
          <div className="trit-fill" style={{ width: `${Math.min(100, barPct)}%` }} />
        </div>
      )}
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  // ── Shared state
  const [key, setKey] = useState("stegokey");
  const [health, setHealth] = useState(null);

  // ── Sender state
  const [coverText, setCoverText] = useState(DEFAULT_COVER);
  const [message, setMessage] = useState("hello");
  const [repeat, setRepeat] = useState(1);

  // ── Analysis state (capacity)
  const [analysis, setAnalysis] = useState(null);
  const analyzeTimer = useRef(null);

  // ── Encode state
  const [encodeResult, setEncodeResult] = useState(null);
  const [encodeBusy, setEncodeBusy] = useState(false);

  // ── Receiver state
  const [stegoText, setStegoText] = useState("");
  const [messageLength, setMessageLength] = useState(5);
  const [decodeRepeat, setDecodeRepeat] = useState(1);

  // ── Decode state
  const [decodeResult, setDecodeResult] = useState(null);
  const [decodeBusy, setDecodeBusy] = useState(false);

  // ── UI state
  const [error, setError] = useState("");
  const [logsOpen, setLogsOpen] = useState(false);

  // ─── Health probe ──────────────────────────────────────────────────────────
  useEffect(() => {
    fetch(`${API}/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ status: "unreachable", nlp_mode: "?" }));
  }, []);

  // ─── Debounced cover text analysis ────────────────────────────────────────
  useEffect(() => {
    clearTimeout(analyzeTimer.current);
    analyzeTimer.current = setTimeout(async () => {
      if (!coverText.trim()) return;
      try {
        const data = await apiPost("/analyze", { text: coverText });
        setAnalysis(data);
      } catch {
        /* silently skip */
      }
    }, 500);
    return () => clearTimeout(analyzeTimer.current);
  }, [coverText]);

  // ─── Needed trits based on message + repeat ────────────────────────────────
  const cleanMsg = useMemo(
    () => message.toLowerCase().replace(/[^a-z]/g, ""),
    [message]
  );
  const neededSlots = cleanMsg.length * 3 * repeat;

  // ─── Encode ───────────────────────────────────────────────────────────────
  async function handleEncode() {
    setEncodeBusy(true);
    setError("");
    setDecodeResult(null);
    try {
      const data = await apiPost("/encode", {
        cover_text: coverText,
        message,
        key,
        repeat: Number(repeat),
      });
      setEncodeResult(data);
      setStegoText(data.stego_text || "");
      setMessageLength(data.effective_message_length ?? cleanMsg.length);
      setDecodeRepeat(Number(repeat));
    } catch (err) {
      setError(err.message);
    } finally {
      setEncodeBusy(false);
    }
  }

  // ─── Decode ───────────────────────────────────────────────────────────────
  async function handleDecode() {
    setDecodeBusy(true);
    setError("");
    try {
      const data = await apiPost("/decode", {
        stego_text: stegoText,
        key,
        message_length: Number(messageLength),
        repeat: Number(decodeRepeat),
      });
      setDecodeResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setDecodeBusy(false);
    }
  }

  // ─── Copy stego text ──────────────────────────────────────────────────────
  const copyStego = useCallback(() => {
    if (stegoText) navigator.clipboard.writeText(stegoText);
  }, [stegoText]);

  // ─── Derived metrics ──────────────────────────────────────────────────────
  const slotsAvail = analysis?.slot_count ?? "—";
  const tritPct =
    encodeResult
      ? (encodeResult.encoded_trits / Math.max(encodeResult.total_trits, 1)) * 100
      : 0;

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div>
      <div className="top-rule" />

      <div className="page">
        {/* ── Header ───────────────────────────────────────────────────────── */}
        <header className="site-header">
          <div>
            <h1 className="header-title font-display">
              STEGO <span className="lab">Lab</span>
            </h1>
            <div className="header-sub">
              Deterministic Linguistic Steganography<br />
              SHA-256 · Base-3 Encoding · ADJ/ADV Hash Slots · POS Verification
            </div>
          </div>
          <div className="header-meta">
            {health && (
              <>
                <span className={`nlp-badge ${health.nlp_mode}`}>
                  NLP: {health.nlp_mode}
                </span>
                <span className="wordnet-badge">
                  WordNet: {health.wordnet === "True" ? "✓ available" : "✗ offline"}
                </span>
              </>
            )}
          </div>
        </header>

        {/* ── Pipeline ─────────────────────────────────────────────────────── */}
        <div className="pipeline">
          <div className="pipeline-node active">Sender</div>
          <span className="pipeline-arrow">→</span>
          <div className="pipeline-node">Cover Text</div>
          <span className="pipeline-arrow">→</span>
          <div className={`pipeline-node ${encodeResult ? "active" : ""}`}>
            SHA-256 Hash Encode
          </div>
          <span className="pipeline-arrow">→</span>
          <div className={`pipeline-node ${stegoText ? "active" : ""}`}>
            Stego Text
          </div>
          <span className="pipeline-arrow">→</span>
          <div className="pipeline-node">Channel</div>
          <span className="pipeline-arrow">→</span>
          <div className={`pipeline-node ${decodeResult ? "active" : ""}`}>
            Majority Vote Decode
          </div>
          <span className="pipeline-arrow">→</span>
          <div className={`pipeline-node ${decodeResult ? "active" : ""}`}>
            Receiver
          </div>
        </div>

        {/* ── Shared Key ───────────────────────────────────────────────────── */}
        <div style={{ marginTop: "1.5rem", maxWidth: "360px" }}>
          <SectionLabel>Shared Secret Key</SectionLabel>
          <Field label="Key (both sides must match)">
            <input
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="e.g. stegokey"
              style={{ fontFamily: "var(--font-mono)" }}
            />
          </Field>
        </div>

        <hr className="section-rule" />

        {/* ── Workspace: Sender | Receiver ─────────────────────────────────── */}
        <div className="workspace">
          {/* ── Sender panel ───────────────────────────────────────────────── */}
          <div className="panel">
            <SectionLabel>01 — Sender</SectionLabel>

            <Field label="Cover Text (adjective-rich prose)">
              <textarea
                value={coverText}
                onChange={(e) => setCoverText(e.target.value)}
                rows={8}
                placeholder="Paste adjective-rich natural language text…"
              />
            </Field>

            <Field label="Secret Message (a–z only)">
              <input
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="hello"
              />
            </Field>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "1rem",
              }}
            >
              <Field label="Repetitions (majority vote)">
                <input
                  type="number"
                  min={1}
                  max={11}
                  value={repeat}
                  onChange={(e) => setRepeat(e.target.value)}
                />
              </Field>
            </div>

            {/* Capacity indicator */}
            <CapacityBar
              slots={analysis?.slot_count ?? 0}
              needed={neededSlots}
            />

            <button
              className="btn btn-primary btn-full"
              disabled={encodeBusy}
              onClick={handleEncode}
            >
              {encodeBusy ? "Encoding…" : "Generate Stego Text →"}
            </button>
          </div>

          {/* ── Receiver panel ─────────────────────────────────────────────── */}
          <div className="panel panel-inverted">
            <SectionLabel>02 — Receiver</SectionLabel>

            <Field label="Stego Text (paste or auto-filled after encode)">
              <textarea
                value={stegoText}
                onChange={(e) => setStegoText(e.target.value)}
                rows={8}
                placeholder="Stego text will appear here after encoding…"
              />
            </Field>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "1rem",
              }}
            >
              <Field label="Expected Message Length">
                <input
                  type="number"
                  min={1}
                  value={messageLength}
                  onChange={(e) => setMessageLength(e.target.value)}
                />
              </Field>
              <Field label="Repetitions">
                <input
                  type="number"
                  min={1}
                  max={11}
                  value={decodeRepeat}
                  onChange={(e) => setDecodeRepeat(e.target.value)}
                />
              </Field>
            </div>

            <button
              className="btn btn-primary btn-full"
              disabled={decodeBusy || !stegoText}
              onClick={handleDecode}
            >
              {decodeBusy ? "Decoding…" : "Decode + Majority Vote →"}
            </button>

            {/* ── Decoded result ──────────────────────────────────────────── */}
            {decodeResult && (
              <div className="decode-result">
                <div className="decode-result-label">Recovered Message</div>
                <div className="decode-result-msg">
                  &ldquo;{decodeResult.decoded_message || "—"}&rdquo;
                </div>
                {decodeResult.pass_messages?.length > 1 && (
                  <div className="decode-passes">
                    {decodeResult.pass_messages.map((p, i) => (
                      <span key={i} className="decode-pass-chip">
                        pass {i + 1}: &quot;{p}&quot;
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ── Error ───────────────────────────────────────────────────────── */}
        {error && <div className="error-banner">{error}</div>}

        <hr className="section-rule" />

        {/* ── Stego text output with carrier highlighting ───────────────── */}
        <div className="stego-output-section">
          <SectionLabel>Stego Text — carrier adjectives highlighted</SectionLabel>

          <div className={`stego-text-box${!stegoText ? " empty" : ""}`}>
            {stegoText
              ? renderHighlighted(stegoText, encodeResult?.carrier_words)
              : "Stego text will appear here after encoding. Highlighted words are carrier adjectives that embed your secret message via SHA-256 hash slot selection."}
          </div>

          {stegoText && (
            <button
              className="btn btn-outline stego-copy-btn"
              onClick={copyStego}
            >
              Copy Stego Text
            </button>
          )}
        </div>

        <hr className="section-rule" />

        {/* ── Metrics ─────────────────────────────────────────────────────── */}
        <SectionLabel>Encoding Metrics</SectionLabel>
        <div className="metrics-grid">
          <MetricCard
            value={
              encodeResult
                ? `${encodeResult.encoded_trits}/${encodeResult.total_trits}`
                : "—"
            }
            label="Trits Encoded"
            sub={tritPct > 0 ? `${Math.round(tritPct)}% coverage` : "run encode first"}
            barPct={tritPct}
          />
          <MetricCard
            value={encodeResult?.encoded_slots ?? "—"}
            label="Slots Used"
            sub={
              encodeResult
                ? `of ${encodeResult.capacity_slots} available`
                : undefined
            }
          />
          <MetricCard
            value={encodeResult?.silent_drops ?? "—"}
            label="Silent Drops"
            sub="slots with no valid pair"
          />
          <MetricCard
            value={
              decodeResult
                ? `${decodeResult.trits_collected ?? "?"}`
                : "—"
            }
            label="Trits Decoded"
            sub={
              decodeResult
                ? `${decodeResult.slots_seen} slots scanned`
                : "run decode first"
            }
          />
        </div>

        <hr className="section-rule" />

        {/* ── Raw JSON logs ────────────────────────────────────────────────── */}
        <div className="logs-section">
          <button
            className="logs-toggle"
            onClick={() => setLogsOpen((o) => !o)}
          >
            <span>Raw JSON — Encode & Decode Payloads</span>
            <span className={`logs-chevron${logsOpen ? " open" : ""}`}>▼</span>
          </button>
          {logsOpen && (
            <div className="logs-body">
              <div className="log-pane">
                <div className="log-pane-title">Encode Response</div>
                <pre className="log-pre">
                  {encodeResult
                    ? JSON.stringify(encodeResult, null, 2)
                    : "No encode run yet."}
                </pre>
              </div>
              <div className="log-pane">
                <div className="log-pane-title">Decode Response</div>
                <pre className="log-pre">
                  {decodeResult
                    ? JSON.stringify(decodeResult, null, 2)
                    : "No decode run yet."}
                </pre>
              </div>
            </div>
          )}
        </div>

        {/* ── Footer ───────────────────────────────────────────────────────── */}
        <footer className="site-footer">
          <span className="footer-copy">
            Deterministic Linguistic Steganography Lab
          </span>
          <div className="footer-tags">
            <span className="tag">SHA-256</span>
            <span className="tag">Base-3</span>
            <span className="tag">ADJ/ADV</span>
            <span className="tag">Majority Vote</span>
            <span className="tag">POS Verified</span>
            <span className="tag">Silent Drop</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
