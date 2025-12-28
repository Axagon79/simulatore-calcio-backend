// Accesso ai dati passati dal template
const allPresets = jsData.allPresets;
const currentPresets = jsData.currentPresets;
const currentAlgo = jsData.currentAlgo;
let masterLocked = jsData.masterLocked;
const savedLocks = jsData.savedLocks;

// Popolamento dinamico preset import
document.querySelector('[name="import_source_algo"]').addEventListener('change', function() {
    const sourceAlgo = this.value;
    const presetSelect = document.getElementById('importPresetSelect');
    presetSelect.innerHTML = '<option value="">-- Seleziona Preset --</option>';
    
    const algoKey = {
        'global': 'GLOBAL',
        '1': 'ALGO_1',
        '2': 'ALGO_2',
        '3': 'ALGO_3',
        '4': 'ALGO_4',
        '5': 'ALGO_5'
    }[sourceAlgo];
    
    const presets = allPresets[algoKey] || {};
    Object.keys(presets).sort().forEach(p => {
        presetSelect.innerHTML += '<option value="' + p + '">' + p + '</option>';
    });
});

// Sync Sliders
function sync(k, src) {
    let r = document.getElementById('r_' + k);
    let n = document.getElementById('n_' + k);
    if(!r || !n) return;
    
    if(src === 'r') {
        n.value = r.value;
    } else {
        r.value = n.value;
    }
}

// Mark Modified
const originalValues = {};
document.querySelectorAll('[name^="val_"]').forEach(el => {
    const k = el.name.replace('val_', '');
    originalValues[k] = parseFloat(el.value);
});

function markModified(k) {
    const current = parseFloat(document.getElementById('n_' + k).value);
    const badge = document.getElementById('mod_' + k);
    if (badge && current !== originalValues[k]) {
        badge.classList.remove('d-none');
    } else if (badge) {
        badge.classList.add('d-none');
    }
}

// Preset Overwrite Check
document.getElementById("presetSelect").addEventListener("change", function () {
    document.getElementById("presetName").value = this.value;
});

function checkOverwrite(e) {
    var name = document.getElementById("presetName").value.trim();

    if (!name) {
        alert("Inserisci un nome per il preset!");
        e.preventDefault();
        return false;
    }

    if (currentPresets.includes(name)) {
        var ok = confirm("Il preset '" + name + "' esiste gia. Vuoi sovrascriverlo?");
        if (!ok) {
            e.preventDefault();
            return false;
        }
    }

    return true;
}

// Master Lock
function toggleMaster() {
    masterLocked = !masterLocked;
    let btn = document.getElementById('masterLock');
    let area = document.getElementById('workingArea');
    
    if(masterLocked) {
        btn.className = "bi bi-lock-fill master-lock locked";
        area.classList.add('disabled-area');
    } else {
        btn.className = "bi bi-unlock-fill master-lock unlocked";
        area.classList.remove('disabled-area');
    }
    
    document.querySelectorAll('.lock-icon').forEach(icon => {
        if(masterLocked) {
            icon.className = "bi bi-lock-fill lock-icon locked";
        } else {
            const isLocked = icon.getAttribute('data-locked') === 'true';
            icon.className = isLocked ? "bi bi-lock-fill lock-icon locked" : "bi bi-unlock lock-icon unlocked";
        }
    });
}

// Single Lock
function toggleLock(k) {
    if(masterLocked) return;
    
    let icon = document.getElementById('icon_' + k);
    let isLocked = icon.getAttribute('data-locked') === 'true';
    let els = [document.getElementById('r_' + k), document.getElementById('n_' + k)];
    
    if(!isLocked) {
        let currentValue = parseFloat(document.getElementById('n_' + k).value);
        icon.setAttribute('data-snapshot', currentValue);
        icon.className = "bi bi-lock-fill lock-icon locked";
        icon.setAttribute('data-locked', 'true');
        els.forEach(e => e.disabled = true);
        
        let badge = document.getElementById('mod_' + k);
        if(badge) {
            badge.textContent = 'SNAPSHOT SALVATO: ' + currentValue;
            badge.classList.remove('d-none');
        }
    } else {
        icon.removeAttribute('data-snapshot');
        icon.className = "bi bi-unlock lock-icon unlocked";
        icon.setAttribute('data-locked', 'false');
        els.forEach(e => e.disabled = false);
    }
}

// Carica lucchetti salvati
Object.keys(savedLocks).forEach(k => {
    if(savedLocks[k] && document.getElementById('icon_' + k)) {
        toggleLock(k);
    }
});

// Salva lucchetti
function saveLockStates() {
    const lockStates = { master_locked: masterLocked, params: {} };
    document.querySelectorAll('.lock-icon').forEach(icon => {
        const k = icon.id.replace('icon_', '');
        lockStates.params[k] = icon.getAttribute('data-locked') === 'true';
    });
    document.getElementById('lockStatesInput').value = JSON.stringify(lockStates);
}

// Handle Save Click
function handleSaveClick() {
    saveLockStates();
    
    if(currentAlgo !== 'global') {
        return true;
    }
    
    let hasOpenLocks = false;
    document.querySelectorAll('.lock-icon').forEach(icon => {
        const isLocked = icon.getAttribute('data-locked') === 'true';
        if(!isLocked && !masterLocked) {
            hasOpenLocks = true;
        }
    });
    
    if(hasOpenLocks) {
        const confirmed = confirm(
            'ATTENZIONE: Stai modificando il MASTER GLOBAL.\n\n' +
            'Le variazioni verranno applicate A CASCATA su tutti gli algoritmi ' +
            'che hanno il lucchetto APERTO verde per i parametri modificati.\n\n' +
            'Vuoi procedere con il salvataggio?'
        );
        return confirmed;
    }
    
    return true;
}

// Inizializzazione
if(masterLocked) {
    toggleMaster();
}