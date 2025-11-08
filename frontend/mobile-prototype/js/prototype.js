// Sortify Mobile Prototype Interactive Script

function navigate(page) {
  // 添加過渡動畫
  document.body.style.opacity = '0.5';
  document.body.style.transition = 'opacity 0.2s';
  
  setTimeout(() => {
    window.location.href = page;
  }, 200);
}

// 模擬上傳進度
function simulateUpload(progressBarId, callback) {
  const progressBar = document.getElementById(progressBarId);
  let progress = 0;
  
  const interval = setInterval(() => {
    progress += 10;
    if (progressBar) {
      progressBar.style.width = progress + '%';
      const progressText = document.getElementById(progressBarId + '-text');
      if (progressText) {
        progressText.textContent = progress + '%';
      }
    }
    
    if (progress >= 100) {
      clearInterval(interval);
      if (callback) callback();
    }
  }, 200);
}

// 模擬分析過程
function simulateAnalysis(steps, callback) {
  let currentStep = 0;
  
  function updateStep() {
    const stepElements = document.querySelectorAll('.process-step');
    if (stepElements[currentStep]) {
      stepElements[currentStep].classList.add('active');
    }
    
    currentStep++;
    if (currentStep < steps) {
      setTimeout(updateStep, 1000);
    } else if (callback) {
      setTimeout(callback, 500);
    }
  }
  
  updateStep();
}

// 頁面載入動畫
document.addEventListener('DOMContentLoaded', () => {
  // 添加淡入動畫
  document.body.style.opacity = '0';
  document.body.style.transition = 'opacity 0.3s';
  
  requestAnimationFrame(() => {
    document.body.style.opacity = '1';
  });
  
  // 為所有可點擊元素添加觸控反饋
  const clickableElements = document.querySelectorAll('.action-item, .mobile-nav-item, .mobile-btn, .document-item');
  
  clickableElements.forEach(element => {
    element.addEventListener('touchstart', function() {
      this.style.transform = 'scale(0.95)';
    });
    
    element.addEventListener('touchend', function() {
      this.style.transform = 'scale(1)';
    });
  });
});

// QR Scanner 模擬
function startQRScanner() {
  const scannerDiv = document.getElementById('qr-scanner');
  if (!scannerDiv) return;
  
  scannerDiv.innerHTML = `
    <div style="width: 100%; aspect-ratio: 1; background: #000; border-radius: 12px; position: relative; overflow: hidden;">
      <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; border: 2px solid #29bf12; box-shadow: 0 0 0 9999px rgba(0,0,0,0.5);"></div>
      <div class="scanner-line" style="position: absolute; top: 0; left: 0; right: 0; height: 2px; background: #29bf12; animation: scan 2s linear infinite;"></div>
    </div>
    <p style="text-align: center; margin-top: 16px; color: #666;">正在掃描...</p>
  `;
  
  // 添加掃描動畫的 CSS
  const style = document.createElement('style');
  style.textContent = `
    @keyframes scan {
      0% { transform: translateY(0); }
      100% { transform: translateY(300px); }
    }
  `;
  document.head.appendChild(style);
  
  // 3秒後模擬掃描成功
  setTimeout(() => {
    scannerDiv.innerHTML = `
      <div class="loading">
        <div class="spinner"></div>
      </div>
      <p style="text-align: center; margin-top: 16px; color: #29bf12;">掃描成功！正在配對...</p>
    `;
    
    setTimeout(() => {
      navigate('home.html');
    }, 1500);
  }, 3000);
}

// 相機控制
function capturePhoto() {
  const cameraWrapper = document.querySelector('.camera-wrapper');
  if (!cameraWrapper) return;
  
  // 閃光效果
  const flash = document.createElement('div');
  flash.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: white; z-index: 9999; animation: flash 0.3s;';
  document.body.appendChild(flash);
  
  const style = document.createElement('style');
  style.textContent = '@keyframes flash { 0%, 100% { opacity: 0; } 50% { opacity: 1; } }';
  document.head.appendChild(style);
  
  setTimeout(() => {
    document.body.removeChild(flash);
    navigate('preview.html');
  }, 300);
}

// 發送消息
function sendMessage() {
  const input = document.getElementById('qa-input');
  if (!input || !input.value.trim()) return;
  
  const messagesDiv = document.getElementById('qa-messages');
  if (!messagesDiv) return;
  
  // 添加用戶消息
  const userMessage = document.createElement('div');
  userMessage.className = 'qa-message user slide-up';
  userMessage.textContent = input.value;
  messagesDiv.appendChild(userMessage);
  
  const question = input.value;
  input.value = '';
  
  // 滾動到底部
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
  
  // 顯示載入動畫
  const loadingMessage = document.createElement('div');
  loadingMessage.className = 'qa-message assistant slide-up';
  loadingMessage.innerHTML = '<div class="loading"><div class="spinner" style="width: 24px; height: 24px;"></div></div>';
  messagesDiv.appendChild(loadingMessage);
  
  // 模擬 AI 回應
  setTimeout(() => {
    messagesDiv.removeChild(loadingMessage);
    
    const aiMessage = document.createElement('div');
    aiMessage.className = 'qa-message assistant slide-up';
    aiMessage.textContent = '根據您上傳的文件，我找到了相關信息。這是一份關於...\n\n（這是模擬回應）';
    messagesDiv.appendChild(aiMessage);
    
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }, 1500);
}

// 處理 Enter 鍵發送
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('qa-input');
  if (input) {
    input.addEventListener('keypress', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }
});

