const form =
    document.getElementById('query-form');

const input =
    document.getElementById('query-input');

const submitBtn =
    document.getElementById('submit-btn');

const entriesContainer =
    document.getElementById('entries');

const screen =
    document.getElementById('screen');

const suggestions =
    document.getElementById('suggestions');

const resetBtn =
    document.getElementById('reset-btn');


// ============================================================
// SUGGESTIONS
// ============================================================

if (suggestions) {

    suggestions.addEventListener(
        'click',
        (e) => {

            const chip =
                e.target.closest('.chip');

            if (!chip) return;

            input.value =
                chip.dataset.q;

            form.requestSubmit();
        }
    );
}


// ============================================================
// RESET
// ============================================================

if (resetBtn) {

    resetBtn.addEventListener(
        'click',
        () => {

            entriesContainer.innerHTML =
                '';

            input.value = '';

            input.focus();
        }
    );
}


// ============================================================
// SUBMIT QUESTION
// ============================================================

form.addEventListener(
    'submit',
    async (e) => {

        e.preventDefault();


        const query =
            input.value.trim();


        if (!query) return;


        // ----------------------------------------------------
        // LOCK UI
        // ----------------------------------------------------

        input.value = '';

        submitBtn.disabled = true;


        const entryEl =
            createPendingEntry(query);


        entriesContainer.appendChild(
            entryEl
        );


        scrollDown();


        const statusEl =
            entryEl.querySelector(
                '.entry-status'
            );


        const aEl =
            entryEl.querySelector(
                '.entry-a'
            );


        try {

            // =================================================
            // API REQUEST
            // =================================================

            const res =
                await fetch(
                    '/ask',
                    {
                        method: 'POST',

                        headers: {
                            'Content-Type':
                                'application/json',

                            'Accept':
                                'text/plain',
                        },

                        body: JSON.stringify(
                            {
                                query: query,
                                top_k: 2,
                            }
                        ),
                    }
                );


            // =================================================
            // HTTP ERROR
            // =================================================

            if (!res.ok) {

                let errorMessage =
                    `Request failed (${res.status}).`;


                try {

                    const errorText =
                        await res.text();


                    if (errorText) {

                        try {

                            const errorJson =
                                JSON.parse(
                                    errorText
                                );


                            if (
                                errorJson.detail
                            ) {

                                errorMessage =
                                    errorJson.detail;

                            } else {

                                errorMessage =
                                    errorText;
                            }


                        } catch (_) {

                            errorMessage =
                                errorText;
                        }
                    }


                } catch (_) {
                    // Keep default message.
                }


                throw new Error(
                    errorMessage
                );
            }


            // =================================================
            // STREAM CHECK
            // =================================================

            if (!res.body) {

                throw new Error(
                    'The server returned no response stream.'
                );
            }


            statusEl.textContent =
                'answering…';


            statusEl.classList.remove(
                'pending'
            );


            // =================================================
            // STREAM READER
            // =================================================

            const reader =
                res.body.getReader();


            const decoder =
                new TextDecoder();


            let raw = '';

            let answerText = '';

            let sourcesParsed = false;

            let sources = [];


            aEl.textContent =
                '';


            // =================================================
            // READ STREAM
            // =================================================

            while (true) {

                const {
                    value,
                    done
                } =
                    await reader.read();


                if (done) {
                    break;
                }


                raw +=
                    decoder.decode(
                        value,
                        {
                            stream: true
                        }
                    );


                // =============================================
                // PARSE HEADER
                // =============================================

                if (!sourcesParsed) {

                    const splitIdx =
                        raw.indexOf(
                            '\n---\n'
                        );


                    if (
                        splitIdx === -1
                    ) {

                        continue;
                    }


                    const header =
                        raw.slice(
                            0,
                            splitIdx
                        );


                    try {

                        const parsed =
                            JSON.parse(
                                header
                            );


                        sources =
                            parsed.sources ||
                            [];


                    } catch (_) {

                        sources = [];
                    }


                    answerText =
                        raw.slice(
                            splitIdx + 5
                        );


                    sourcesParsed =
                        true;


                } else {

                    const splitIdx =
                        raw.indexOf(
                            '\n---\n'
                        );


                    if (
                        splitIdx !== -1
                    ) {

                        answerText =
                            raw.slice(
                                splitIdx + 5
                            );

                    } else {

                        answerText =
                            raw;
                    }
                }


                // =============================================
                // UPDATE ANSWER
                // =============================================

                aEl.innerHTML =
                    `<span class="prompt-sym">&gt;</span>` +
                    escapeHtml(
                        answerText
                    );


                scrollDown();
            }


            // =================================================
            // FLUSH DECODER
            // =================================================

            const finalText =
                decoder.decode();


            if (finalText) {

                raw += finalText;
            }


            // =================================================
            // FINAL ANSWER
            // =================================================

            if (sourcesParsed) {

                const splitIdx =
                    raw.indexOf(
                        '\n---\n'
                    );


                if (
                    splitIdx !== -1
                ) {

                    answerText =
                        raw.slice(
                            splitIdx + 5
                        );

                } else {

                    answerText =
                        raw;
                }


                aEl.innerHTML =
                    `<span class="prompt-sym">&gt;</span>` +
                    escapeHtml(
                        answerText
                    );
            }


            // =================================================
            // STATUS
            // =================================================

            statusEl.textContent =
                'answered';


            statusEl.classList.add(
                'ok'
            );


            // =================================================
            // SOURCES
            // =================================================

            if (
                sources.length
            ) {

                const refsEl =
                    document.createElement(
                        'div'
                    );


                refsEl.className =
                    'refs';


                refsEl.innerHTML =
                    sources
                        .map(
                            (s) => {

                                const file =
                                    escapeHtml(
                                        String(
                                            s.file ??
                                            ''
                                        )
                                    );


                                const chunk =
                                    escapeHtml(
                                        String(
                                            s.chunk ??
                                            ''
                                        )
                                    );


                                return (
                                    `<span class="ref-tag">` +
                                    `${file} #${chunk}` +
                                    `</span>`
                                );
                            }
                        )
                        .join('');


                entryEl.appendChild(
                    refsEl
                );
            }


        } catch (err) {

            // =================================================
            // ERROR
            // =================================================

            statusEl.textContent =
                'error';


            statusEl.classList.add(
                'err'
            );


            const message =
                err &&
                err.message
                    ? err.message
                    : 'The query failed.';


            aEl.innerHTML =
                `<span class="prompt-sym">&gt;</span>` +
                escapeHtml(
                    message
                );


        } finally {

            // =================================================
            // UNLOCK UI
            // =================================================

            submitBtn.disabled =
                false;


            input.focus();


            scrollDown();
        }
    }
);


// ============================================================
// CREATE PENDING ENTRY
// ============================================================

function createPendingEntry(
    query
) {

    const div =
        document.createElement(
            'div'
        );


    div.className =
        'entry';


    div.innerHTML = `
        <span class="entry-status pending">
            retrieving…
        </span>

        <p class="entry-q">
            <span class="prompt-sym">$</span>
            ${escapeHtml(query)}
        </p>

        <p class="entry-a">
            <span class="dots-anim">
                <span></span>
                <span></span>
                <span></span>
            </span>
        </p>
    `;


    return div;
}


// ============================================================
// ESCAPE HTML
// ============================================================

function escapeHtml(
    str
) {

    const div =
        document.createElement(
            'div'
        );


    div.textContent =
        String(str);


    return div.innerHTML;
}


// ============================================================
// SCROLL
// ============================================================

function scrollDown() {

    if (!screen) return;


    screen.scrollTop =
        screen.scrollHeight;
}
