async function sendMessage() {
    const input = document.getElementById('userInput');
    const chatBox = document.getElementById('chatBox');
    const message = input.value.trim();

    if (!message) return;

    // 1. Añadir mensaje del usuario a la pantalla
    appendMessage(message, 'user');
    input.value = '';

    // 2. Mostrar indicador de "IA pensando..."
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message ai typing';
    typingDiv.innerHTML = `<div class="bubble">...</div>`;
    chatBox.appendChild(typingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });
        const data = await response.json();
        
        // Remover indicador de carga y añadir respuesta real
        chatBox.removeChild(typingDiv);
        appendMessage(data.response, 'ai');
    } catch (error) {
        chatBox.removeChild(typingDiv);
        appendMessage("Error al conectar con el servidor.", 'ai');
    }
}

function appendMessage(text, sender) {
    const chatBox = document.getElementById('chatBox');
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender}`;
    msgDiv.innerHTML = `<div class="bubble">${text}</div>`;
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// Escuchar el evento de subida de archivo
document.getElementById('fileInput').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    document.getElementById('fileStatus').innerText = "Subiendo...";

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        document.getElementById('fileStatus').innerHTML = `<i class="fas fa-check-circle"></i> ${file.name}`;
        appendMessage(`Archivo "${file.name}" cargado con éxito. ¿Qué quieres analizar?`, 'ai');
    } catch (error) {
        document.getElementById('fileStatus').innerText = "Error al subir";
    }
});

// Permitir enviar con la tecla Enter
document.getElementById('userInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});