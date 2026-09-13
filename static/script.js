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

    if (!res.ok || !res.body) throw new Error('Request failed.');

    statusEl.textContent = 'answering…';
    statusEl.classList.remove('pending');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    let raw = '';          // sab kuch jo ab tak server se aaya (header + answer)
    let answerText = '';   // sirf answer ka hissa, header nikalne ke baad
    let sourcesParsed = false;
    let sources = [];

    aEl.textContent = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      raw += decoder.decode(value, { stream: true });

      if (!sourcesParsed) {
        const splitIdx = raw.indexOf('\n---\n');
        if (splitIdx === -1) {
          continue;   // header abhi poora nahi aaya, wait karo
        }
        const header = raw.slice(0, splitIdx);
        try {
          sources = JSON.parse(header).sources || [];
        } catch (_) {
          sources = [];
        }
        answerText = raw.slice(splitIdx + 5);   // jo bhi header ke baad bacha hai
        sourcesParsed = true;
      } else {
        answerText = raw.slice(raw.indexOf('\n---\n') + 5);
      }

      aEl.innerHTML = `<span class="prompt-sym">&gt;</span>${escapeHtml(answerText)}`;
      scrollDown();
    }

    statusEl.textContent = 'answered';
    statusEl.classList.add('ok');

    if (sources.length) {
      const refsEl = document.createElement('div');
      refsEl.className = 'refs';
      refsEl.innerHTML = sources
        .map(s => `<span class="ref-tag">${escapeHtml(s.file)} #${s.chunk}</span>`)
        .join('');
      entryEl.appendChild(refsEl);
    }
  } catch (err) {
    statusEl.textContent = 'error';
    statusEl.classList.add('err');
    aEl.innerHTML = `<span class="prompt-sym">&gt;</span>${escapeHtml(err.message || 'The query failed.')}`;
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

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function scrollDown() {
  screen.scrollTop = screen.scrollHeight;
}
