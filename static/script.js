const $ = (id) => document.getElementById(id);

function showStatus(text, isError = false) {
    $('status').textContent = text;
    $('status').className = isError ? 'error' : '';
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

function selectPattern(prefix, extension) {
    $('prefix').value = prefix;
    $('extension').value = extension;
}

function renderPatterns(patterns) {
    const container = $('patterns');
    container.replaceChildren();
    $('patterns-section').hidden = false;
    if (patterns.length === 0) {
        container.textContent = 'No files found.';
        return;
    }
    patterns.forEach(([[prefix, ext], count], i) => {
        const label = document.createElement('label');
        label.className = 'pattern';
        const radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'pattern';
        radio.checked = i === 0;
        radio.addEventListener('change', () => selectPattern(prefix, ext));
        label.append(radio, ` ${prefix}*${ext} — ${count} files`);
        container.appendChild(label);
    });
    selectPattern(...patterns[0][0]);
}

async function setDirectory(directory) {
    try {
        const result = await postJson('/set_directory', {directory});
        $('directory').value = result.directory;
        renderPatterns(result.patterns);
        showStatus('');
    } catch (error) {
        showStatus(`Error setting directory: ${error.message}`, true);
    }
}

async function loadModels() {
    try {
        const models = await (await fetch('/models')).json();
        $('model').replaceChildren(...models.map((m) => new Option(m, m)));
        if (models.length === 0) showStatus('No Ollama models found. Is Ollama running?', true);
    } catch (error) {
        showStatus(`Error loading models: ${error.message}`, true);
    }
}

$('set-dir-btn').addEventListener('click', () => setDirectory($('directory').value));
$('directory').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') setDirectory($('directory').value);
});

$('choose-dir-btn').addEventListener('click', async () => {
    if (!window.pywebview) {
        showStatus('Folder picker is only available in the desktop app.', true);
        return;
    }
    const directory = await window.pywebview.api.choose_directory();
    if (directory) await setDirectory(directory);
});

$('rename-btn').addEventListener('click', async () => {
    const buttons = ['rename-btn', 'set-dir-btn', 'choose-dir-btn'].map($);
    buttons.forEach((b) => { b.disabled = true; });
    showStatus('Renaming… this can take a while.');
    try {
        const result = await postJson('/rename_files', {
            prefix: $('prefix').value,
            extension: $('extension').value,
            model: $('model').value,
        });
        const lines = [`Renamed: ${result.renamed_count}, failed: ${result.failed_count}`];
        result.failed_files.forEach(([file, error]) => lines.push(`${file}: ${error}`));
        await setDirectory($('directory').value);
        showStatus(lines.join('\n'), result.failed_count > 0);
    } catch (error) {
        showStatus(`Error renaming files: ${error.message}`, true);
    } finally {
        buttons.forEach((b) => { b.disabled = false; });
    }
});

loadModels();
