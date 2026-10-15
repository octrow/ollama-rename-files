const $ = (id) => document.getElementById(id);
const PREVIEW_DELAY_MS = 250;

const state = {files: [], running: false, stopRequested: false, previewTimer: null};

function showStatus(text, isError = false) {
    $('status').textContent = text;
    $('status').classList.toggle('error', isError);
}

function plural(n, word) {
    return `${n} ${word}${n === 1 ? '' : 's'}`;
}

async function postJson(url, body) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || response.statusText);
    return data;
}

/* ---------- folder & patterns ---------- */

function renderPatterns(patterns) {
    const container = $('patterns');
    container.replaceChildren();
    $('controls').hidden = false;
    if (patterns.length === 0) {
        container.textContent = 'This folder has no files.';
        return;
    }
    patterns.forEach(([[prefix, ext], count], i) => {
        const label = document.createElement('label');
        label.className = 'chip';
        const radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'pattern';
        radio.checked = i === 0;
        radio.addEventListener('change', () => usePattern(prefix, ext));
        const text = document.createElement('span');
        const hint = document.createElement('small');
        hint.textContent = plural(count, 'file');
        text.append(`${prefix}*${ext}`, hint);
        label.append(radio, text);
        container.appendChild(label);
    });
}

function usePattern(prefix, extension) {
    $('prefix').value = prefix;
    $('extension').value = extension;
    preview();
}

async function scan(directory) {
    try {
        const result = await postJson('/set_directory', {directory});
        $('directory').value = result.directory;
        renderPatterns(result.patterns);
        if (result.patterns.length) usePattern(...result.patterns[0][0]);
        else renderFiles([]);
        showStatus('');
    } catch (error) {
        showStatus(error.message, true);
    }
}

/** Re-count patterns after a run, keeping the finished old → new list on screen. */
async function refreshPatterns() {
    try {
        const result = await postJson('/set_directory', {directory: $('directory').value});
        renderPatterns(result.patterns);
        document.querySelectorAll('input[name="pattern"]').forEach((r) => { r.checked = false; });
    } catch (error) {
        console.warn('Pattern refresh failed', error);  // the run summary in the status bar matters more
    }
}

/* ---------- file list ---------- */

function renderFiles(names) {
    state.files = names.map((name) => {
        const row = document.createElement('li');
        row.className = 'row';
        row.dataset.state = 'pending';
        const old = document.createElement('span');
        old.className = 'old';
        old.textContent = name;
        const arrow = document.createElement('span');
        arrow.className = 'arrow';
        arrow.setAttribute('aria-hidden', 'true');
        arrow.textContent = '→';
        const fresh = document.createElement('span');
        fresh.className = 'new';
        row.append(old, arrow, fresh);
        return {name, row, fresh};
    });
    $('files').replaceChildren(...state.files.map((f) => f.row));

    const hasFiles = names.length > 0;
    $('empty').hidden = hasFiles;
    if (!hasFiles && !$('controls').hidden) {
        $('empty').textContent = 'No files match. Pick another pattern or edit the name and extension.';
    }
    updateRenameButton();
}

function setRow(file, rowState, text = '', asMark = false) {
    file.row.dataset.state = rowState;
    if (asMark) {
        const mark = document.createElement('mark');
        mark.textContent = text;
        file.fresh.replaceChildren(mark);
    } else {
        file.fresh.textContent = text;
    }
}

async function preview() {
    try {
        const names = await postJson('/preview', {
            prefix: $('prefix').value,
            extension: $('extension').value,
        });
        renderFiles(names);
    } catch (error) {
        showStatus(error.message, true);
    }
}

function schedulePreview() {
    clearTimeout(state.previewTimer);
    state.previewTimer = setTimeout(preview, PREVIEW_DELAY_MS);
    document.querySelectorAll('input[name="pattern"]').forEach((r) => { r.checked = false; });
}

/* ---------- models ---------- */

async function loadModels() {
    try {
        const models = await (await fetch('/models')).json();
        $('model').replaceChildren(...models.map((m) => new Option(m, m)));
        $('model').disabled = models.length === 0;
        if (models.length === 0) showStatus('No Ollama models found. Start Ollama and pull a model, then reopen this window.', true);
    } catch (error) {
        showStatus(`Couldn't reach Ollama: ${error.message}`, true);
    }
    updateRenameButton();
}

/* ---------- rename run ---------- */

function updateRenameButton() {
    const button = $('rename-btn');
    if (state.running) {
        button.textContent = 'Stop';
        button.classList.add('stop');
        button.disabled = false;
        return;
    }
    const pending = state.files.filter((f) => f.row.dataset.state === 'pending').length;
    button.classList.remove('stop');
    button.textContent = pending ? `Rename ${plural(pending, 'file')}` : 'Rename files';
    button.disabled = pending === 0 || !$('model').value;
}

function setInputsLocked(locked) {
    ['directory', 'browse-btn', 'scan-btn', 'prefix', 'extension', 'model'].forEach((id) => { $(id).disabled = locked; });
    document.querySelectorAll('input[name="pattern"]').forEach((r) => { r.disabled = locked; });
}

async function renameAll() {
    const queue = state.files.filter((f) => f.row.dataset.state === 'pending');
    const model = $('model').value;
    let backupDir = null;
    let renamed = 0;
    let failed = 0;

    state.running = true;
    state.stopRequested = false;
    setInputsLocked(true);
    updateRenameButton();

    for (const [i, file] of queue.entries()) {
        if (state.stopRequested) break;
        showStatus(`Renaming ${i + 1} of ${queue.length} with ${model}…`);
        setRow(file, 'working');
        try {
            const result = await postJson('/rename_file', {file: file.name, model, backup_dir: backupDir});
            backupDir = result.backup_dir;
            if (result.ok) {
                setRow(file, 'done', result.new_name, true);
                renamed += 1;
            } else {
                setRow(file, 'failed', result.error);
                failed += 1;
            }
        } catch (error) {
            setRow(file, 'failed', error.message);
            failed += 1;
        }
    }

    state.running = false;
    setInputsLocked(false);
    await refreshPatterns();
    updateRenameButton();
    const parts = [`Renamed ${plural(renamed, 'file')}`];
    if (failed) parts.push(`${failed} failed`);
    if (state.stopRequested) parts.push('stopped early');
    const backupNote = backupDir ? ` Originals are in ${backupDir}.` : '';
    showStatus(`${parts.join(', ')}.${backupNote}`, failed > 0);
}

/* ---------- wiring ---------- */

$('folder-form').addEventListener('submit', (event) => {
    event.preventDefault();
    scan($('directory').value);
});

$('browse-btn').addEventListener('click', async () => {
    if (!window.pywebview) {
        showStatus('Browse works in the desktop app. Type the folder path here instead.', true);
        return;
    }
    const directory = await window.pywebview.api.choose_directory();
    if (directory) await scan(directory);
});

$('prefix').addEventListener('input', schedulePreview);
$('extension').addEventListener('input', schedulePreview);
$('model').addEventListener('change', updateRenameButton);

$('rename-btn').addEventListener('click', () => {
    if (state.running) {
        state.stopRequested = true;
        showStatus('Stopping after the current file…');
    } else {
        renameAll();
    }
});

loadModels();
