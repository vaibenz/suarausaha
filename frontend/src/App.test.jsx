import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App.jsx';

const EMPTY_SUMMARY = {
  day: '2026-10-13', sales_total: 0, cash_received: 0, credit_outstanding: 0,
  expenses_total: 0, profit_estimate: 0, transactions: 0, top_items: [],
};

function json(body, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

let entries;
let summary;

function installFetch({ audio = false } = {}) {
  entries = [];
  summary = { ...EMPTY_SUMMARY };
  global.fetch = vi.fn((url, options = {}) => {
    if (url === '/api/health') return json({ status: 'ok', engine: 'offline', audio });
    if (url === '/api/entries' && !options.method) return json(entries);
    if (url === '/api/summary') return json(summary);
    if (url === '/api/entries/text') {
      const { text } = JSON.parse(options.body);
      if (text.includes('kopi lima ribu')) {
        const entry = { id: 1, kind: 'sale', item: 'kopi', quantity: 3, unit_price: 5000, amount: 15000,
          payment_method: 'tunai', customer: null, created_at: '2026-10-13T09:15:00+07:00', day: '2026-10-13' };
        entries = [entry];
        summary = { ...summary, sales_total: 15000, profit_estimate: 15000, transactions: 1 };
        return json({ entries: [entry], errors: [], messages: ['Tercatat penjualan 3 kopi, total Rp15.000.'],
          speech: 'Tercatat penjualan 3 kopi, total Rp15.000.', summary: null, undone: null });
      }
      return json({ entries: [], errors: ['Harga untuk kopi belum disebut.'], messages: [],
        speech: 'Harga untuk kopi belum disebut.', summary: null, undone: null });
    }
    if (url === '/api/entries/last') {
      const last = entries[0];
      entries = [];
      return last ? json(last) : json({ detail: 'No entries' }, 404);
    }
    return json({ detail: 'not found' }, 404);
  });
}

async function axeViolations(container) {
  const results = await axe.run(container, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'] },
    rules: { 'color-contrast': { enabled: false } }, // checked from tokens in theme.test.js
  });
  return results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
}

beforeEach(() => {
  installFetch();
  window.speechSynthesis = undefined;
});

async function renderApp() {
  const utils = render(<App />);
  await screen.findByText('Belum ada catatan hari ini.');
  return utils;
}

describe('accessibility', () => {
  it('has no axe violations on first load', async () => {
    const { container } = await renderApp();
    expect(await axeViolations(container)).toEqual([]);
  });

  it('has no axe violations with entries, feedback and high contrast on', async () => {
    const user = userEvent.setup();
    const { container } = await renderApp();
    await user.click(screen.getByRole('button', { name: /kontras tinggi/i }));
    await user.type(screen.getByLabelText('Atau ketik transaksi'), 'jual tiga kopi lima ribu{Enter}');
    await screen.findByRole('table');
    expect(await axeViolations(container)).toEqual([]);
  });

  it('exposes one h1 and a sensible heading outline', async () => {
    await renderApp();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'Catat transaksi', 'Ringkasan hari ini', 'Catatan terbaru']);
  });

  it('provides a skip link as the first focusable element', async () => {
    const user = userEvent.setup();
    await renderApp();
    await user.tab();
    expect(screen.getByRole('link', { name: 'Langsung ke pencatatan' })).toHaveFocus();
  });
});

describe('recording by text and keyboard', () => {
  it('announces the confirmation in a polite live region and returns focus to the input', async () => {
    const user = userEvent.setup();
    await renderApp();
    const input = screen.getByLabelText('Atau ketik transaksi');
    await user.type(input, 'jual tiga kopi lima ribu{Enter}');

    const live = screen.getByTestId('live-region');
    expect(live).toHaveAttribute('role', 'status');
    expect(live).toHaveAttribute('aria-live', 'polite');
    await waitFor(() => expect(live).toHaveTextContent('Berhasil: Tercatat penjualan 3 kopi, total Rp15.000.'));
    expect(input).toHaveFocus();
    expect(input).toHaveValue('');

    const table = await screen.findByRole('table');
    const row = within(table).getAllByRole('row')[1];
    expect(within(row).getByText('Jual')).toBeInTheDocument();
    expect(within(row).getByText('Rp15.000')).toBeInTheDocument();
    expect(screen.getByText('Penjualan').nextSibling).toHaveTextContent('Rp15.000');
  });

  it('states errors in words, not just colour', async () => {
    const user = userEvent.setup();
    await renderApp();
    await user.type(screen.getByLabelText('Atau ketik transaksi'), 'jual tiga kopi{Enter}');
    await waitFor(() =>
      expect(screen.getByTestId('live-region')).toHaveTextContent('Perhatian: Harga untuk kopi belum disebut.'));
  });

  it('asks for input instead of sending an empty request', async () => {
    const user = userEvent.setup();
    await renderApp();
    await user.click(screen.getByRole('button', { name: 'Catat' }));
    expect(screen.getByTestId('live-region')).toHaveTextContent('Tulis atau ucapkan transaksinya dulu.');
    expect(fetch).not.toHaveBeenCalledWith('/api/entries/text', expect.anything());
  });

  it('can undo the last entry', async () => {
    const user = userEvent.setup();
    await renderApp();
    await user.type(screen.getByLabelText('Atau ketik transaksi'), 'jual tiga kopi lima ribu{Enter}');
    await screen.findByRole('table');
    await user.click(screen.getByRole('button', { name: 'Hapus catatan terakhir' }));
    await waitFor(() => expect(screen.getByTestId('live-region')).toHaveTextContent('Catatan terakhir dihapus: kopi.'));
  });
});

describe('settings', () => {
  it('toggles report state with aria-pressed and persist', async () => {
    const user = userEvent.setup();
    await renderApp();
    const contrast = screen.getByRole('button', { name: /kontras tinggi/i });
    expect(contrast).toHaveAttribute('aria-pressed', 'false');
    await user.click(contrast);
    expect(contrast).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('app-root')).toHaveClass('theme-contrast');
    expect(localStorage.getItem('su.contrast')).toBe('true');
  });

  it('reads confirmations aloud in Indonesian when enabled', async () => {
    const speakSpy = vi.fn();
    window.speechSynthesis = { speak: speakSpy, cancel: vi.fn() };
    global.SpeechSynthesisUtterance = function (text) {
      this.text = text;
    };
    const user = userEvent.setup();
    await renderApp();
    await user.type(screen.getByLabelText('Atau ketik transaksi'), 'jual tiga kopi lima ribu{Enter}');
    await waitFor(() => expect(speakSpy).toHaveBeenCalled());
    expect(speakSpy.mock.calls[0][0]).toMatchObject({ text: 'Tercatat penjualan 3 kopi, total Rp15.000.', lang: 'id-ID' });
  });
});

describe('voice input', () => {
  it('explains when voice is unavailable and keeps the button focusable', async () => {
    await renderApp();
    const mic = screen.getByRole('button', { name: 'Tekan untuk bicara' });
    expect(mic).toHaveAttribute('aria-disabled', 'true');
    expect(mic).not.toBeDisabled(); // still reachable by keyboard so the explanation is discoverable
    expect(mic).toHaveAccessibleDescription(/belum mendukung suara/);
  });

  it('transcribes in id-ID with the Web Speech API and records the result', async () => {
    let instance;
    window.SpeechRecognition = vi.fn(function () {
      instance = this;
      this.start = vi.fn();
      this.stop = vi.fn(() => this.onend?.());
    });
    const user = userEvent.setup();
    await renderApp();
    const mic = screen.getByRole('button', { name: 'Tekan untuk bicara' });
    expect(mic).toHaveAttribute('aria-disabled', 'false');
    await user.click(mic);
    expect(instance.lang).toBe('id-ID');
    expect(screen.getByRole('button', { name: 'Berhenti merekam' })).toHaveAttribute('aria-pressed', 'true');

    await act(async () => {
      instance.onresult({ results: [[{ transcript: 'jual tiga kopi lima ribu' }]] });
      instance.onend();
    });
    await waitFor(() =>
      expect(screen.getByTestId('live-region')).toHaveTextContent('Tercatat penjualan 3 kopi, total Rp15.000.'));
    expect(screen.getByRole('button', { name: 'Tekan untuk bicara' })).toHaveAttribute('aria-pressed', 'false');
  });
});
