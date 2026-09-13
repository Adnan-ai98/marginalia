const form = document.getElementById('query-form');
const input = document.getElementById('query-input');
const submitBtn = document.getElementById('submit-btn');
const entriesContainer = document.getElementById('entries');
const screen = document.getElementById('screen');
const suggestions = document.getElementById('suggestions');
const resetBtn = document.getElementById('reset-btn');

suggestions.addEventListener('click', (e) => {
  const chip = e.target.closest('.chip');
  if (!chip) return;
  input.value = chip.dataset.q;
  form.requestSubmit();
});

resetBtn.addEventListener('click', () => {
  entriesContainer.innerHTML = '';
  input.value = '';
  input.focus();
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = input.value.trim();
  if (!query) return;

  input.value = '';
  submitBtn.disabled = true;

  const entryEl = createPendingEntry(query);
  entriesContainer.appendChild(entryEl);
  scrollDown();

  const statusEl = entryEl.querySelector('.entry-status');
  const aEl = entryEl.querySelector('.entry-a');

  try {
    const res = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, top_k: 3 })
    });

    if (!res.ok) throw new Error('Request failed.');

    statusEl.textContent = 'answering…';
    statusEl.classList.remove('pending');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let sourcesParsed = false;
    let sources = [];
    aEl.textContent = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      if (!sourcesParsed) {
        const splitIdx = buffer.indexOf('\n---\n');
        if (splitIdx === -1) continue;   // header abhi poora nahi aaya
        const header = buffer.slice(0, splitIdx);
        sources = JSON.parse(header).sources || [];
        buffer = buffer.slice(splitIdx + 5);
        sourcesParsed = true;
      }

      aEl.innerHTML = `<span class="prompt-sym">&gt;</span>${escapeHtml(buffer)}`;
      scrollDown();
    }

    statusEl.textContent = 'answered';
    statusEl.classList.add('ok');

    if (sources.length) {
      const refsEl = document.createElement('div');
      refsEl.className = 'refs';
      refsEl.innerHTML = sources.map(s => `<span class="ref-tag">${escapeHtml(s.file)} #${s.chunk}</span>`).join('');
      entryEl.appendChild(refsEl);
    }
  } catch (err) {
    statusEl.textContent = 'error';
    statusEl.classList.add('err');
    aEl.innerHTML = `<span class="prompt-sym">&gt;</span>${escapeHtml(err.message || 'Failed.')}`;
  } finally {
    submitBtn.disabled = false;
    scrollDown();
  }
});

function createPendingEntry(query) {
  const div = document.createElement('div');
  div.className = 'entry';
  div.innerHTML = `
    <span class="entry-status pending">retrieving…</span>
    <p class="entry-q"><span class="prompt-sym">$</span>${escapeHtml(query)}</p>
    <p class="entry-a"><span class="dots-anim"><span></span><span></span><span></span></span></p>
  `;
  return div;
}

function fillEntry(entryEl, data) {
  const statusEl = entryEl.querySelector('.entry-status');
  statusEl.textContent = 'answered';
  statusEl.classList.remove('pending');
  statusEl.classList.add('ok');

  const aEl = entryEl.querySelector('.entry-a');
  aEl.innerHTML = `<span class="prompt-sym">&gt;</span>${escapeHtml(data.answer)}`;

  if (data.sources && data.sources.length) {
    const refsEl = document.createElement('div');
    refsEl.className = 'refs';
    refsEl.innerHTML = data.sources
      .map(s => `<span class="ref-tag">${escapeHtml(s.file)} #${s.chunk}</span>`)
      .join('');
    entryEl.appendChild(refsEl);
  }
}

function fillEntryError(entryEl, message) {
  const statusEl = entryEl.querySelector('.entry-status');
  statusEl.textContent = 'error';
  statusEl.classList.remove('pending');
  statusEl.classList.add('err');

  const aEl = entryEl.querySelector('.entry-a');
  aEl.innerHTML = `<span class="prompt-sym">&gt;</span>${escapeHtml(message || 'The query failed.')}`;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function scrollDown() {
  screen.scrollTop = screen.scrollHeight;
}
