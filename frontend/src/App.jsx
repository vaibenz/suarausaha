import { useCallback, useEffect, useRef, useState } from 'react';
import { api, rupiah } from './api.js';
import { cssVars } from './theme.js';
import { detectVoiceMode, useVoice } from './useVoice.js';

function load(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : JSON.parse(v);
  } catch {
    return fallback;
  }
}

function save(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: settings last for this visit only */
  }
}

function speak(text) {
  if (!text || typeof window === 'undefined' || !window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'id-ID';
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

function Toggle({ pressed, onChange, children }) {
  return (
    <button type="button" className="toggle" aria-pressed={pressed} onClick={() => onChange(!pressed)}>
      <span className="toggle-state" aria-hidden="true">{pressed ? 'Aktif' : 'Mati'}</span>
      {children}
    </button>
  );
}

const KIND_LABEL = { sale: 'Jual', expense: 'Beli' };
const PAY_LABEL = { tunai: 'Tunai', qris: 'QRIS', transfer: 'Transfer', hutang: 'Hutang' };

export default function App() {
  const [highContrast, setHighContrast] = useState(() => load('su.contrast', false));
  const [largeText, setLargeText] = useState(() => load('su.large', false));
  const [readAloud, setReadAloud] = useState(() => load('su.speak', true));
  const [serverAudio, setServerAudio] = useState(false);
  const [entries, setEntries] = useState([]);
  const [summary, setSummary] = useState(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(null); // { tone: 'success' | 'error', text }
  const inputRef = useRef(null);

  useEffect(() => save('su.contrast', highContrast), [highContrast]);
  useEffect(() => save('su.large', largeText), [largeText]);
  useEffect(() => save('su.speak', readAloud), [readAloud]);

  const refresh = useCallback(async () => {
    try {
      const [e, s] = await Promise.all([api.entries(), api.summary()]);
      setEntries(e);
      setSummary(s);
    } catch (err) {
      setFeedback({ tone: 'error', text: `Gagal memuat data: ${err.message}` });
    }
  }, []);

  useEffect(() => {
    refresh();
    api.health().then((h) => setServerAudio(Boolean(h.audio))).catch(() => {});
  }, [refresh]);

  const handleOutcome = useCallback(
    (outcome) => {
      const ok = outcome.entries.length > 0 || outcome.summary || outcome.undone;
      const message = outcome.speech || (ok ? 'Tercatat.' : 'Maaf, belum mengerti.');
      setFeedback({ tone: outcome.errors.length && !ok ? 'error' : 'success', text: message });
      if (readAloud) speak(message);
      refresh();
    },
    [readAloud, refresh],
  );

  const submitText = useCallback(
    async (value) => {
      const trimmed = value.trim();
      if (!trimmed) {
        setFeedback({ tone: 'error', text: 'Tulis atau ucapkan transaksinya dulu.' });
        inputRef.current?.focus();
        return;
      }
      setBusy(true);
      try {
        handleOutcome(await api.recordText(trimmed));
        setText('');
      } catch (err) {
        setFeedback({ tone: 'error', text: `Gagal mencatat: ${err.message}` });
      } finally {
        setBusy(false);
        inputRef.current?.focus();
      }
    },
    [handleOutcome],
  );

  const submitAudio = useCallback(
    async (blob) => {
      setBusy(true);
      try {
        handleOutcome(await api.recordVoice(blob));
      } catch (err) {
        setFeedback({ tone: 'error', text: `Gagal mencatat: ${err.message}` });
      } finally {
        setBusy(false);
      }
    },
    [handleOutcome],
  );

  const voiceMode = detectVoiceMode(serverAudio);
  const voice = useVoice({
    mode: voiceMode,
    onText: (heard) => {
      setText(heard);
      submitText(heard);
    },
    onAudio: submitAudio,
    onError: (msg) => setFeedback({ tone: 'error', text: msg }),
  });
  const voiceUnavailable = voiceMode === 'none';

  const undo = async () => {
    try {
      const e = await api.undo();
      handleOutcome({ entries: [], errors: [], undone: e, speech: `Catatan terakhir dihapus: ${e.item}.` });
    } catch {
      setFeedback({ tone: 'error', text: 'Belum ada catatan untuk dihapus.' });
    }
  };

  const rootClass = ['app', highContrast ? 'theme-contrast' : 'theme-default', largeText ? 'text-large' : '']
    .filter(Boolean)
    .join(' ');

  return (
    <div className={rootClass} style={cssVars(highContrast ? 'contrast' : 'default')} data-testid="app-root">
      <a className="skip-link" href="#catat">
        Langsung ke pencatatan
      </a>
      <header className="header">
        <div>
          <h1>SuaraUsaha</h1>
          <p className="tagline">Catat jualan dan belanja warung cukup dengan suara.</p>
        </div>
        <div className="settings" role="group" aria-label="Pengaturan tampilan">
          <Toggle pressed={highContrast} onChange={setHighContrast}>
            Kontras tinggi
          </Toggle>
          <Toggle pressed={largeText} onChange={setLargeText}>
            Teks besar
          </Toggle>
          <Toggle pressed={readAloud} onChange={setReadAloud}>
            Bacakan hasil
          </Toggle>
        </div>
      </header>

      <main id="main">
        <section className="card" aria-labelledby="catat-title" id="catat" tabIndex={-1}>
          <h2 id="catat-title">Catat transaksi</h2>
          <div className="voice">
            <button
              type="button"
              className={`mic${voice.listening ? ' mic-on' : ''}`}
              aria-pressed={voice.listening}
              aria-disabled={voiceUnavailable || busy}
              aria-describedby="mic-help"
              onClick={() => {
                if (voiceUnavailable || busy) return;
                voice.listening ? voice.stop() : voice.start();
              }}
            >
              <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" className="mic-icon">
                <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z" />
              </svg>
              <span>{voice.listening ? 'Berhenti merekam' : 'Tekan untuk bicara'}</span>
            </button>
            <p id="mic-help" className="hint">
              {voiceUnavailable
                ? 'Peramban ini belum mendukung suara. Silakan ketik transaksi di bawah.'
                : 'Contoh: "jual tiga kopi lima ribu" atau "bu Sri ngutang dua indomie tiga ribu lima ratus".'}
            </p>
          </div>

          <form
            className="type-form"
            onSubmit={(e) => {
              e.preventDefault();
              submitText(text);
            }}
          >
            <label htmlFor="transaksi">Atau ketik transaksi</label>
            <div className="row">
              <input
                id="transaksi"
                ref={inputRef}
                type="text"
                inputMode="text"
                autoComplete="off"
                value={text}
                onChange={(e) => setText(e.target.value)}
                aria-describedby="type-help"
              />
              <button type="submit" className="primary" disabled={busy}>
                {busy ? 'Menyimpan' : 'Catat'}
              </button>
            </div>
            <p id="type-help" className="hint">
              Sebut jumlah, nama barang dan harga satuan.
            </p>
          </form>

          <div className="feedback-slot">
            <div role="status" aria-live="polite" aria-atomic="true" data-testid="live-region">
              {feedback && (
                <p className={`feedback feedback-${feedback.tone}`}>
                  <span className="feedback-label">{feedback.tone === 'error' ? 'Perhatian:' : 'Berhasil:'}</span>{' '}
                  {feedback.text}
                </p>
              )}
            </div>
          </div>
        </section>

        <section className="card" aria-labelledby="ringkasan-title">
          <h2 id="ringkasan-title">Ringkasan hari ini</h2>
          {summary ? (
            <dl className="summary">
              <div>
                <dt>Penjualan</dt>
                <dd>{rupiah(summary.sales_total)}</dd>
              </div>
              <div>
                <dt>Pengeluaran</dt>
                <dd>{rupiah(summary.expenses_total)}</dd>
              </div>
              <div>
                <dt>Perkiraan untung</dt>
                <dd>{rupiah(summary.profit_estimate)}</dd>
              </div>
              <div>
                <dt>Hutang pelanggan</dt>
                <dd>{rupiah(summary.credit_outstanding)}</dd>
              </div>
            </dl>
          ) : (
            <p>Memuat ringkasan.</p>
          )}
        </section>

        <section className="card" aria-labelledby="riwayat-title">
          <div className="section-head">
            <h2 id="riwayat-title">Catatan terbaru</h2>
            <button type="button" className="secondary" onClick={undo} disabled={entries.length === 0}>
              Hapus catatan terakhir
            </button>
          </div>
          {entries.length === 0 ? (
            <p>Belum ada catatan hari ini.</p>
          ) : (
            <div className="table-wrap" role="region" aria-label="Tabel catatan, bisa digeser ke samping" tabIndex={0}>
              <table>
                <caption className="visually-hidden">Daftar transaksi terbaru, yang paling baru di atas</caption>
                <thead>
                  <tr>
                    <th scope="col">Jam</th>
                    <th scope="col">Jenis</th>
                    <th scope="col">Barang</th>
                    <th scope="col">Jumlah</th>
                    <th scope="col">Total</th>
                    <th scope="col">Bayar</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e) => (
                    <tr key={e.id}>
                      <td>{e.created_at.slice(11, 16)}</td>
                      <td>{KIND_LABEL[e.kind]}</td>
                      <td>{e.item}</td>
                      <td>{e.quantity}</td>
                      <td>{rupiah(e.amount)}</td>
                      <td>{e.payment_method === 'hutang' && e.customer ? `Hutang (${e.customer})` : PAY_LABEL[e.payment_method]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
