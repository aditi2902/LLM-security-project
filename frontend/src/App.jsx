import React, { useState, useEffect } from 'react';
import { Search, ShieldAlert, ShieldCheck, Globe, AlertTriangle, Terminal, Eye, Database, Ban, FileSearch, Trash2, Key } from 'lucide-react';
import './index.css';

const Typewriter = ({ text }) => {
  const [displayed, setDisplayed] = useState('');
  
  useEffect(() => {
    if (!text) {
      setDisplayed('');
      return;
    }
    
    let i = 0;
    const interval = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) clearInterval(interval);
    }, 15);
    
    return () => clearInterval(interval);
  }, [text]);

  return <span className={displayed.length < text?.length ? "typing" : ""}>{displayed}</span>;
};

const StatusCard = ({ type, title, subtitle }) => {
  const icons = {
    success: <ShieldCheck size={24} color="var(--success)" />,
    warning: <AlertTriangle size={24} color="var(--warning)" />,
    danger: <ShieldAlert size={24} color="var(--danger)" />
  };

  return (
    <div className="status-card">
      <div className={`pulse-dot ${type}`}></div>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
        <div style={{ marginTop: '-2px' }}>{icons[type]}</div>
        <div className="status-content">
          <h4>{title}</h4>
          {subtitle && <p>{subtitle}</p>}
        </div>
      </div>
    </div>
  );
};

function App() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('answer');

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);
    setActiveTab('answer');

    try {
      const res = await fetch('http://localhost:8000/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      });

      if (!res.ok) throw new Error('Backend error: ' + res.status);
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err.message || 'Failed to connect to backend.');
    } finally {
      setLoading(false);
    }
  };

  const isChat = result?.intent === 'CHAT';
  const memoryWrites = result?.memory_write || [];
  const successfulMemories = memoryWrites.filter(m => m.action !== "Reject");
  const rejectedMemories = memoryWrites.filter(m => m.action === "Reject");
  const egressBlocked = result?.validation_result?.safe === false;

  return (
    <div className="app-container">
      <header className="hero">
        <div className="logo-container">
          <Eye size={48} className="logo-icon" />
          <h1>Trust<span>Lens</span></h1>
        </div>
        <p className="subtitle">AI Observability & Security Platform. Gain total visibility into how your AI reasons, what it trusts, and what it rejects.</p>
      </header>

      <form className="search-container" onSubmit={handleSearch}>
        <input
          type="text"
          className="search-input"
          placeholder="Enter a prompt, URL, or test file..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={loading}
          autoComplete="off"
        />
        <button type="submit" className="search-button" disabled={loading || !query.trim()}>
          {loading ? <div className="loader"><Search size={20} /></div> : <Search size={20} />}
          {loading ? 'Observing...' : 'Trace'}
        </button>
      </form>

      {error && (
        <div className="glass-panel error-panel" style={{ animationDelay: '0.2s' }}>
          <StatusCard type="danger" title="Telemetry Error" subtitle={error} />
        </div>
      )}

      {result && (
        <div className="dashboard-grid">
          
          {/* Stage 1: Edge Security Alert */}
          {result.blocked && !result.prompt_security?.safe && (
            <div className="glass-panel" style={{ gridColumn: '1 / -1' }}>
              <StatusCard type="danger" title="Ingress Blocked" subtitle={`Malicious payload detected at edge: ${result.reason}`} />
            </div>
          )}

          {/* Main Content Area */}
          {!result.blocked && (
            <div className="glass-panel" style={{ gridColumn: '1 / -1', padding: 0, overflow: 'hidden' }}>
              <div className="observability-tabs">
                <button className={`obs-tab ${activeTab === 'answer' ? 'active' : ''}`} onClick={() => setActiveTab('answer')}>
                  <Terminal size={16} /> Final Output
                </button>
                {!isChat && (
                  <>
                    <button className={`obs-tab ${activeTab === 'searched' ? 'active' : ''}`} onClick={() => setActiveTab('searched')}>
                      <FileSearch size={16} /> What it Searched
                    </button>
                    <button className={`obs-tab ${activeTab === 'ignored' ? 'active' : ''}`} onClick={() => setActiveTab('ignored')}>
                      <Trash2 size={16} /> What it Ignored
                    </button>
                    <button className={`obs-tab ${activeTab === 'trusted' ? 'active' : ''}`} onClick={() => setActiveTab('trusted')}>
                      <ShieldCheck size={16} /> Why it Trusted
                    </button>
                  </>
                )}
                <button className={`obs-tab ${activeTab === 'remembered' ? 'active' : ''}`} onClick={() => setActiveTab('remembered')}>
                  <Database size={16} /> What it Remembered
                </button>
                <button className={`obs-tab ${activeTab === 'rejected' ? 'active' : ''}`} onClick={() => setActiveTab('rejected')}>
                  <Ban size={16} /> What it Rejected
                </button>
              </div>

              <div className="obs-content">
                {activeTab === 'answer' && (
                  <div className="obs-panel">
                    <div className="final-answer">
                      <Terminal size={20} className="bg-icon" />
                      <div className="text-content">
                        {egressBlocked ? (
                          <span className="blocked-text">Egress Blocked by Response Validator.</span>
                        ) : (
                          <Typewriter text={result.answer} />
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === 'searched' && (
                  <div className="obs-panel">
                    <h3>Raw Context Fetched</h3>
                    <p className="obs-desc">This is the unfiltered data retrieved from the web or document before security checks.</p>
                    <div className="raw-text">{result.raw_content}</div>
                  </div>
                )}

                {activeTab === 'ignored' && (
                  <div className="obs-panel">
                    <h3>Removed Threat Vectors</h3>
                    <p className="obs-desc">Content explicitly stripped out by the Threat Analyzer to protect the LLM.</p>
                    <pre>{JSON.stringify(result.removed_content || "No threats detected.", null, 2)}</pre>
                  </div>
                )}

                {activeTab === 'trusted' && (
                  <div className="obs-panel">
                    <h3>Sanitized Context Window</h3>
                    <p className="obs-desc">The finalized, safe content injected into the LLM's context window. (Risk Score: {result.risk_score})</p>
                    <div className="raw-text">{result.sanitized_content}</div>
                  </div>
                )}

                {activeTab === 'remembered' && (
                  <div className="obs-panel">
                    <h3>Committed to Long-Term Memory</h3>
                    <p className="obs-desc">Information that successfully passed the Memory Validator and was stored.</p>
                    {successfulMemories.length > 0 ? (
                      <pre>{JSON.stringify(successfulMemories, null, 2)}</pre>
                    ) : (
                      <div className="empty-state">No new memories stored.</div>
                    )}
                  </div>
                )}

                {activeTab === 'rejected' && (
                  <div className="obs-panel">
                    <h3>Blocked Actions</h3>
                    <p className="obs-desc">Egress blocks or rejected memory writes due to policy violations.</p>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      {egressBlocked && (
                         <StatusCard type="danger" title="Egress Blocked" subtitle={result.validation_result?.reason} />
                      )}
                      {rejectedMemories.length > 0 && (
                        <div>
                          <h4>Rejected Memory Writes</h4>
                          <pre>{JSON.stringify(rejectedMemories, null, 2)}</pre>
                        </div>
                      )}
                      {!egressBlocked && rejectedMemories.length === 0 && (
                        <div className="empty-state">No blocked actions.</div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default App;
