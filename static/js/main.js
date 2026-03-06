// ── Flash auto-dismiss ───────────────────────────────────────────────
setTimeout(() => {
  document.querySelectorAll('.flash').forEach(el => {
    el.style.transition = 'opacity 0.5s';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 500);
  });
}, 4000);

// ── File drag-and-drop + preview ────────────────────────────────────
const dropZone   = document.getElementById('dropZone');
const fileInput  = document.getElementById('fileInput');
const previewArea= document.getElementById('previewArea');
const previewImg = document.getElementById('previewImg');
const previewName= document.getElementById('previewName');
const clearBtn   = document.getElementById('clearBtn');
const analyzeBtn = document.getElementById('analyzeBtn');
const uploadForm = document.getElementById('uploadForm');

if (dropZone && fileInput) {
  dropZone.addEventListener('click', () => fileInput.click());

  ['dragenter','dragover'].forEach(e => {
    dropZone.addEventListener(e, ev => { ev.preventDefault(); dropZone.classList.add('drag-over'); });
  });
  ['dragleave','drop'].forEach(e => {
    dropZone.addEventListener(e, ev => { ev.preventDefault(); dropZone.classList.remove('drag-over'); });
  });
  dropZone.addEventListener('drop', ev => {
    const file = ev.dataTransfer.files[0];
    if (file) setPreview(file);
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) setPreview(fileInput.files[0]);
  });

  clearBtn && clearBtn.addEventListener('click', () => {
    fileInput.value = '';
    previewArea.style.display = 'none';
    dropZone.style.display = 'block';
  });

  uploadForm && uploadForm.addEventListener('submit', () => {
    if (analyzeBtn) {
      analyzeBtn.querySelector('.btn-text').style.display = 'none';
      analyzeBtn.querySelector('.btn-loading').style.display = 'inline';
      analyzeBtn.disabled = true;
    }
  });
}

function setPreview(file) {
  const allowed = ['image/png','image/jpeg','image/gif','image/webp','image/bmp'];
  if (!allowed.includes(file.type)) {
    alert('Invalid file type. Please upload an image.');
    return;
  }
  if (file.size > 16 * 1024 * 1024) {
    alert('File too large. Maximum size is 16 MB.');
    return;
  }
  const reader = new FileReader();
  reader.onload = e => {
    previewImg.src = e.target.result;
    previewName.textContent = file.name;
    dropZone.style.display = 'none';
    previewArea.style.display = 'block';
    // Transfer to real input if dropped
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
  };
  reader.readAsDataURL(file);
}
