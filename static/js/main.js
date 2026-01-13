// --- UTILIDADES DE UI ---
function appendMessage(text, sender) {
    const chatBox = document.getElementById('chatBox');
    if (!chatBox) return;

    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender}`;
    msgDiv.innerHTML = `<div class="bubble">${text.replace(/\n/g, '<br>')}</div>`;
    
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// --- LÓGICA DE CHAT ---
async function sendMessage() {
    const input = document.getElementById('userInput');
    const chatBox = document.getElementById('chatBox');
    if (!input || !chatBox) return;

    const message = input.value.trim();
    if (!message) return;

    appendMessage(message, 'user');
    input.value = '';

    const typingDiv = document.createElement('div');
    typingDiv.className = 'message ai typing';
    typingDiv.innerHTML = `<div class="bubble"><i class="fas fa-spinner fa-spin"></i> Analizando datos...</div>`;
    chatBox.appendChild(typingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });
        
        const data = await response.json();
        chatBox.removeChild(typingDiv);
        
        if (data.response) {
            appendMessage(data.response, 'ai');
            
            // ACTUALIZACIÓN DINÁMICA DE CRÉDITOS
            if (data.nuevo_conteo !== undefined) {
                const creditElement = document.querySelector('.credits-value');
                if (creditElement) {
                    const currentText = creditElement.innerText;
                    const total = currentText.split('/')[1] || '5'; 
                    creditElement.innerHTML = `<i class="fas fa-bolt text-warning me-1"></i> ${data.nuevo_conteo} / ${total.trim()}`;
                    
                    // Efecto de feedback visual
                    creditElement.style.color = "#f1c40f";
                    setTimeout(() => { creditElement.style.color = "white"; }, 500);
                }
            }
        }
    } catch (error) {
        if (chatBox.contains(typingDiv)) chatBox.removeChild(typingDiv);
        appendMessage("Error de conexión con el servidor.", 'ai');
    }
}

// --- EVENT LISTENERS ---

// Subida de Archivos con Manejo de Errores (Créditos)
const fileInput = document.getElementById('fileInput');
if (fileInput) {
    fileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        const statusLabel = document.getElementById('fileStatus');
        if (statusLabel) statusLabel.innerHTML = `<i class="fas fa-sync fa-spin"></i> Procesando...`;

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (response.ok && data.success) {
                if (statusLabel) statusLabel.innerHTML = `<i class="fas fa-check-circle text-success"></i> ${file.name}`;
                appendMessage(`✅ **${file.name}** cargado. ¿Qué insight deseas extraer?`, 'ai');
            } else {
                // AQUÍ CAPTURAMOS EL ERROR DE CRÉDITOS AGOTADOS
                if (statusLabel) statusLabel.innerHTML = `<i class="fas fa-exclamation-triangle text-danger"></i> Error`;
                appendMessage(`❌ ${data.message || data.error || "No se pudo subir el archivo"}`, 'ai');
            }
        } catch (error) {
            if (statusLabel) statusLabel.innerText = "Error de conexión";
            console.error("Upload Error:", error);
        }
    });
}

// Tecla Enter
const userInput = document.getElementById('userInput');
if (userInput) {
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            sendMessage();
        }
    });
}