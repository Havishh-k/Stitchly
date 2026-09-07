document.addEventListener('DOMContentLoaded', () => {
    // --- DOM ELEMENTS ---
    // Landing & Modal
    const openModalBtn = document.getElementById('open-modal-btn');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const modalOverlay = document.getElementById('modal-overlay');
    
    // Views
    const uploadView = document.getElementById('upload-view');
    const processingView = document.getElementById('processing-view');
    const resultView = document.getElementById('result-view');
    
    // Upload Elements
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const previewArea = document.getElementById('preview-area');
    const previewGallery = document.getElementById('preview-gallery');
    const fileCountSpan = document.getElementById('file-count');
    
    // Buttons
    const btnSubmit = document.getElementById('btn-submit');
    const btnReset = document.getElementById('reset-btn');
    const btnClearAll = document.getElementById('clear-btn');
    const btnTryAgain = document.getElementById('btn-try-again');
    const btnDownload = document.getElementById('btn-download');
    
    // Result
    const resultImage = document.getElementById('result-image');
    const formatSelect = document.getElementById('format-select');
    
    // Error
    const errorBanner = document.getElementById('error-banner');
    const errorMessage = document.getElementById('error-message');

    // State
    let selectedFiles = []; // Array of File objects
    let sortableInstance = null;
    let currentResultUrl = '';

    // --- MODAL LOGIC ---
    function openModal() {
        modalOverlay.classList.remove('hidden');
        document.body.style.overflow = 'hidden'; // Prevent background scrolling
    }

    function closeModal() {
        modalOverlay.classList.add('hidden');
        document.body.style.overflow = '';
        // Don't reset state on close, let them come back to it unless they hit reset
    }

    openModalBtn.addEventListener('click', openModal);
    closeModalBtn.addEventListener('click', closeModal);
    
    // Close on outside click
    modalOverlay.addEventListener('click', (e) => {
        if (e.target === modalOverlay) closeModal();
    });

    // --- UPLOAD & DRAG/DROP LOGIC ---
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    });

    fileInput.addEventListener('change', function() {
        handleFiles(this.files);
        this.value = ''; // Reset input so same file can be selected again if needed
    });

    function handleFiles(files) {
        hideError();
        
        const newFiles = Array.from(files).filter(file => {
            const validTypes = ['image/jpeg', 'image/jpg', 'image/png'];
            if (!validTypes.includes(file.type)) {
                showError(`Invalid file type: ${file.name}. Only JPG/PNG allowed.`);
                return false;
            }
            if (file.size > 10 * 1024 * 1024) {
                showError(`File too large: ${file.name}. Max 10MB.`);
                return false;
            }
            return true;
        });

        if (selectedFiles.length + newFiles.length > 3) {
            showError("Maximum of 3 images allowed.");
            return;
        }

        selectedFiles = [...selectedFiles, ...newFiles];
        updateUI();
    }

    // --- UI UPDATES ---
    function updateUI() {
        fileCountSpan.textContent = selectedFiles.length;
        
        if (selectedFiles.length > 0) {
            previewArea.classList.remove('hidden');
            renderPreviews();
        } else {
            previewArea.classList.add('hidden');
            previewGallery.innerHTML = '';
        }

        // Enable stitch button if 2 or 3 files
        btnSubmit.disabled = !(selectedFiles.length >= 2 && selectedFiles.length <= 3);
    }

    function renderPreviews() {
        previewGallery.innerHTML = '';
        
        selectedFiles.forEach((file, index) => {
            const reader = new FileReader();
            
            const div = document.createElement('div');
            div.className = 'preview-item';
            div.dataset.index = index; // Store original index
            
            const img = document.createElement('img');
            
            const removeBtn = document.createElement('button');
            removeBtn.className = 'remove-btn';
            removeBtn.innerHTML = '<i class="ph-bold ph-x"></i>';
            removeBtn.onclick = (e) => {
                e.stopPropagation();
                // Find current index based on DOM in case of reordering
                const currIdx = Array.from(previewGallery.children).indexOf(div);
                selectedFiles.splice(currIdx, 1);
                updateUI();
            };
            
            div.appendChild(img);
            div.appendChild(removeBtn);
            previewGallery.appendChild(div);
            
            reader.onload = (e) => { img.src = e.target.result; };
            reader.readAsDataURL(file);
        });

        // Initialize or update SortableJS for drag-to-reorder
        if (sortableInstance) {
            sortableInstance.destroy();
        }
        
        sortableInstance = new Sortable(previewGallery, {
            animation: 150,
            ghostClass: 'sortable-ghost',
            onEnd: function (evt) {
                // Update selectedFiles array based on new DOM order
                const itemEl = evt.item;
                const newIndex = evt.newIndex;
                const oldIndex = evt.oldIndex;
                
                // Reorder array
                const movedItem = selectedFiles.splice(oldIndex, 1)[0];
                selectedFiles.splice(newIndex, 0, movedItem);
            },
        });
    }

    function resetState() {
        selectedFiles = [];
        updateUI();
        hideError();
        showView(uploadView);
        currentResultUrl = '';
    }

    btnReset.addEventListener('click', resetState);
    btnClearAll.addEventListener('click', resetState);
    btnTryAgain.addEventListener('click', resetState);

    function showView(viewToShow) {
        [uploadView, processingView, resultView].forEach(view => {
            view.classList.add('hidden');
        });
        viewToShow.classList.remove('hidden');
    }

    function showError(msg) {
        errorMessage.textContent = msg;
        errorBanner.classList.remove('hidden');
    }

    function hideError() {
        errorBanner.classList.add('hidden');
        errorMessage.textContent = '';
    }

    // --- SUBMISSION ---
    btnSubmit.addEventListener('click', async () => {
        if (selectedFiles.length < 2 || selectedFiles.length > 3) {
            showError("Please select exactly 2 or 3 images.");
            return;
        }

        const formData = new FormData();
        // Append in the visual order
        selectedFiles.forEach(file => {
            formData.append('images[]', file);
        });
        
        // Pass the format selection
        const format = formatSelect.value;
        formData.append('format', format);

        showView(processingView);
        hideError();

        try {
            const response = await fetch('/api/stitch', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || "Failed to stitch images");
            }

            // Success
            currentResultUrl = data.image_url;
            resultImage.src = currentResultUrl;
            
            // Set up download button
            const extension = format === 'png' ? 'png' : 'jpg';
            btnDownload.href = currentResultUrl;
            btnDownload.download = `panorama.${extension}`;
            
            showView(resultView);

        } catch (error) {
            showError(error.message);
            showView(uploadView);
        }
    });

    // Update download link when format changes
    formatSelect.addEventListener('change', () => {
        // We'll need a backend endpoint to convert the existing result if we want to change it after stitching,
        // or we just use the original request format. Since we appended format to the POST request,
        // the returned image is already in that format. 
        // For now, let's just update the download attribute extension.
        const format = formatSelect.value;
        const extension = format === 'png' ? 'png' : 'jpg';
        btnDownload.download = `panorama.${extension}`;
    });
});
