// ============================================================
// ELEMENTS
// ============================================================

const form =
    document.getElementById("query-form");

const input =
    document.getElementById("query-input");

const submitBtn =
    document.getElementById("submit-btn");

const entriesContainer =
    document.getElementById("entries");

const screen =
    document.getElementById("screen");

const suggestions =
    document.getElementById("suggestions");

const resetBtn =
    document.getElementById("reset-btn");

const paperSelect =
    document.getElementById("paper-select");

const paperList =
    document.getElementById("paper-list");

const paperStatus =
    document.getElementById("paper-status");

const scopeBadge =
    document.getElementById("scope-badge");

const uploadBtn =
    document.getElementById("upload-btn");

const fileInput =
    document.getElementById("file-input");

const uploadStatus =
    document.getElementById("upload-status");


// ============================================================
// STATE
// ============================================================

let papers = [];


// ============================================================
// LOAD PAPERS
// ============================================================

async function loadPapers() {

    try {

        const response =
            await fetch("/papers");

        if (!response.ok) {

            throw new Error(
                `Failed to load papers (${response.status}).`
            );
        }

        const data =
            await response.json();

        papers =
            data.papers || [];

        renderPaperSelector();

        renderPaperList();

        updateScope();


    } catch (error) {

        console.error(
            "Paper loading error:",
            error
        );

        paperStatus.textContent =
            "Could not load indexed papers.";

        paperList.innerHTML = `
            <li class="paper-error">
                Failed to load papers.
            </li>
        `;
    }
}


// ============================================================
// RENDER PAPER SELECTOR
// ============================================================

function renderPaperSelector() {

    const currentValue =
        paperSelect.value;

    paperSelect.innerHTML = "";


    const allOption =
        document.createElement("option");

    allOption.value = "";

    allOption.textContent =
        "All Papers";

    paperSelect.appendChild(
        allOption
    );


    papers.forEach(
        (paper) => {

            const option =
                document.createElement("option");

            option.value =
                paper.filename;

            option.textContent =
                paper.title;

            option.title =
                paper.filename;

            paperSelect.appendChild(
                option
            );
        }
    );


    if (
        currentValue &&
        papers.some(
            (paper) =>
                paper.filename === currentValue
        )
    ) {

        paperSelect.value =
            currentValue;

    } else {

        paperSelect.value = "";
    }
}


// ============================================================
// RENDER PAPER LIST
// ============================================================

function renderPaperList() {

    if (!papers.length) {

        paperList.innerHTML = `
            <li class="paper-loading">
                No papers indexed yet.
            </li>
        `;

        paperStatus.textContent =
            "Indexed 0 papers.";

        return;
    }


    paperList.innerHTML =
        papers
            .map(
                (paper, index) => {

                    const number =
                        String(index + 1)
                            .padStart(2, "0");

                    return `
                        <li>
                            <span class="tag">
                                [${number}]
                            </span>

                            <span class="paper-title">
                                ${escapeHtml(
                                    paper.title
                                )}
                            </span>

                            <span class="dim paper-meta">
                                — ${paper.chunks} chunks
                            </span>
                        </li>
                    `;
                }
            )
            .join("");


    const totalChunks =
        papers.reduce(
            (total, paper) =>
                total +
                Number(paper.chunks || 0),
            0
        );


    paperStatus.textContent =
        `Indexed ${papers.length} papers → ` +
        `${totalChunks} chunks → pgvector`;
}


// ============================================================
// PAPER SELECTION
// ============================================================

paperSelect.addEventListener(
    "change",
    () => {

        updateScope();

        updatePlaceholder();

        input.focus();
    }
);


// ============================================================
// UPDATE SCOPE BADGE
// ============================================================

function updateScope() {

    const selected =
        paperSelect.value;

    if (!selected) {

        scopeBadge.textContent =
            "ALL PAPERS";

        scopeBadge.classList.remove(
            "paper-selected"
        );

        return;
    }


    const paper =
        papers.find(
            (item) =>
                item.filename === selected
        );


    if (paper) {

        scopeBadge.textContent =
            truncate(
                paper.title,
                32
            );

    } else {

        scopeBadge.textContent =
            "SELECTED PAPER";
    }


    scopeBadge.classList.add(
        "paper-selected"
    );
}


// ============================================================
// PLACEHOLDER
// ============================================================

function updatePlaceholder() {

    const selected =
        paperSelect.value;


    if (!selected) {

        input.placeholder =
            "ask a question about the papers…";

        return;
    }


    const paper =
        papers.find(
            (item) =>
                item.filename === selected
        );


    if (paper) {

        input.placeholder =
            `ask about ${paper.title}…`;

    } else {

        input.placeholder =
            "ask a question about the selected paper…";
    }
}


// ============================================================
// UPLOAD BUTTON
// ============================================================

uploadBtn.addEventListener(
    "click",
    () => {

        fileInput.click();
    }
);


// ============================================================
// FILE SELECTED
// ============================================================

fileInput.addEventListener(
    "change",
    async () => {

        const file =
            fileInput.files[0];

        if (!file) return;

        await uploadPaper(file);

        fileInput.value = "";
    }
);


// ============================================================
// UPLOAD PAPER
// ============================================================

async function uploadPaper(file) {

    const maxSize =
        25 * 1024 * 1024;


    if (file.size > maxSize) {

        showUploadStatus(
            "File is larger than 25 MB.",
            "error"
        );

        return;
    }


    const allowed =
        [
            ".pdf",
            ".md",
            ".txt",
        ];


    const lowerName =
        file.name.toLowerCase();


    const isAllowed =
        allowed.some(
            (extension) =>
                lowerName.endsWith(
                    extension
                )
        );


    if (!isAllowed) {

        showUploadStatus(
            "Only PDF, MD, and TXT files are supported.",
            "error"
        );

        return;
    }


    uploadBtn.disabled = true;


    showUploadStatus(
        `Indexing ${file.name}…`,
        "loading"
    );


    try {

        const formData =
            new FormData();

        formData.append(
            "file",
            file
        );


        const response =
            await fetch(
                "/upload",
                {
                    method: "POST",
                    body: formData,
                }
            );


        let data = null;

        try {

            data =
                await response.json();

        } catch (_) {

            data = null;
        }


        if (!response.ok) {

            const message =
                data &&
                data.detail
                    ? data.detail
                    : `Upload failed (${response.status}).`;

            throw new Error(
                message
            );
        }


        showUploadStatus(
            `✓ Added ${data.filename} — ${data.chunks} chunks`,
            "success"
        );


        await loadPapers();


        // Automatically select newly uploaded paper.
        paperSelect.value =
            data.filename;

        updateScope();

        updatePlaceholder();

        input.focus();


    } catch (error) {

        console.error(
            "Upload error:",
            error
        );

        showUploadStatus(
            error.message ||
            "Upload failed.",
            "error"
        );

    } finally {

        uploadBtn.disabled =
            false;
    }
}


// ============================================================
// UPLOAD STATUS
// ============================================================

function showUploadStatus(
    message,
    type
) {

    uploadStatus.textContent =
        message;

    uploadStatus.className =
        "upload-status";


    if (type) {

        uploadStatus.classList.add(
            type
        );
    }
}


// ============================================================
// SUGGESTIONS
// ============================================================

if (suggestions) {

    suggestions.addEventListener(
        "click",
        (event) => {

            const chip =
                event.target.closest(
                    ".chip"
                );

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
        "click",
        () => {

            entriesContainer.innerHTML =
                "";

            input.value =
                "";

            input.focus();
        }
    );
}


// ============================================================
// SUBMIT QUESTION
// ============================================================

form.addEventListener(
    "submit",
    async (event) => {

        event.preventDefault();


        const query =
            input.value.trim();


        if (!query) return;


        const selectedPaper =
            paperSelect.value ||
            null;


        // ----------------------------------------------------
        // LOCK UI
        // ----------------------------------------------------

        input.value = "";

        submitBtn.disabled = true;


        const entryEl =
            createPendingEntry(
                query,
                selectedPaper
            );


        entriesContainer.appendChild(
            entryEl
        );


        scrollDown();


        const statusEl =
            entryEl.querySelector(
                ".entry-status"
            );


        const aEl =
            entryEl.querySelector(
                ".entry-a"
            );


        try {

            // =================================================
            // API REQUEST
            // =================================================

            const response =
                await fetch(
                    "/ask",
                    {
                        method: "POST",

                        headers: {
                            "Content-Type":
                                "application/json",

                            "Accept":
                                "text/plain",
                        },

                        body:
                            JSON.stringify(
                                {
                                    query:
                                        query,

                                    top_k:
                                        2,

                                    source_file:
                                        selectedPaper,
                                }
                            ),
                    }
                );


            // =================================================
            // HTTP ERROR
            // =================================================

            if (!response.ok) {

                let errorMessage =
                    `Request failed (${response.status}).`;


                try {

                    const errorText =
                        await response.text();


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
                    // Keep default.
                }


                throw new Error(
                    errorMessage
                );
            }


            // =================================================
            // STREAM CHECK
            // =================================================

            if (!response.body) {

                throw new Error(
                    "The server returned no response stream."
                );
            }


            statusEl.textContent =
                "answering…";

            statusEl.classList.remove(
                "pending"
            );


            // =================================================
            // STREAM READER
            // =================================================

            const reader =
                response.body.getReader();

            const decoder =
                new TextDecoder();


            let raw = "";

            let answerText =
                "";

            let sourcesParsed =
                false;

            let sources =
                [];


            aEl.textContent =
                "";


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

                    const splitIndex =
                        raw.indexOf(
                            "\n---\n"
                        );


                    if (
                        splitIndex === -1
                    ) {

                        continue;
                    }


                    const header =
                        raw.slice(
                            0,
                            splitIndex
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
                            splitIndex + 5
                        );


                    sourcesParsed =
                        true;


                } else {

                    const splitIndex =
                        raw.indexOf(
                            "\n---\n"
                        );


                    if (
                        splitIndex !== -1
                    ) {

                        answerText =
                            raw.slice(
                                splitIndex + 5
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

                const splitIndex =
                    raw.indexOf(
                        "\n---\n"
                    );


                if (
                    splitIndex !== -1
                ) {

                    answerText =
                        raw.slice(
                            splitIndex + 5
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
                "answered";

            statusEl.classList.add(
                "ok"
            );


            // =================================================
            // SOURCES
            // =================================================

            if (
                sources.length
            ) {

                const refsEl =
                    document.createElement(
                        "div"
                    );


                refsEl.className =
                    "refs";


                refsEl.innerHTML =
                    sources
                        .map(
                            (source) => {

                                const file =
                                    escapeHtml(
                                        String(
                                            source.file ??
                                            ""
                                        )
                                    );


                                const chunk =
                                    escapeHtml(
                                        String(
                                            source.chunk ??
                                            ""
                                        )
                                    );


                                return `
                                    <span class="ref-tag">
                                        ${file} #${chunk}
                                    </span>
                                `;
                            }
                        )
                        .join("");


                entryEl.appendChild(
                    refsEl
                );
            }


        } catch (error) {

            // =================================================
            // ERROR
            // =================================================

            console.error(
                "Query error:",
                error
            );


            statusEl.textContent =
                "error";


            statusEl.classList.add(
                "err"
            );


            const message =
                error &&
                error.message
                    ? error.message
                    : "The query failed.";


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
    query,
    selectedPaper
) {

    const div =
        document.createElement(
            "div"
        );


    div.className =
        "entry";


    const scopeText =
        selectedPaper
            ? `paper: ${selectedPaper}`
            : "scope: all papers";


    div.innerHTML = `

        <span class="entry-status pending">
            retrieving…
        </span>

        <p class="entry-q">

            <span class="prompt-sym">
                $
            </span>

            ${escapeHtml(query)}

        </p>

        <div class="entry-scope">
            ${escapeHtml(scopeText)}
        </div>

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
    value
) {

    const div =
        document.createElement(
            "div"
        );


    div.textContent =
        String(value);


    return div.innerHTML;
}


// ============================================================
// TRUNCATE
// ============================================================

function truncate(
    value,
    maxLength
) {

    const text =
        String(value || "");


    if (
        text.length <= maxLength
    ) {

        return text;
    }


    return (
        text.slice(
            0,
            maxLength - 1
        ) + "…"
    );
}


// ============================================================
// SCROLL
// ============================================================

function scrollDown() {

    if (!screen) return;


    screen.scrollTop =
        screen.scrollHeight;
}


// ============================================================
// INITIALIZE
// ============================================================

loadPapers();

updatePlaceholder();

input.focus();
