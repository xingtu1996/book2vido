// Book2Vido GUI v3
console.log('Book2Vido GUI v3 loaded');

// 全局状态
let state = {
  docLoaded: false,
  filePath: '',
  generating: false,
  selectedChapters: new Set(),
  chatHistory: [],
  pollTimer: null,
  currentVideo: null
};

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', () => {
  checkEnv();
  loadHistory();
  loadVoices();
  bindEvents();
  loadChatFromStorage();
});

// ========== Toast 提示 ==========
function showToast(msg, type = 'info') {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.className = 'toast show ' + type;
  setTimeout(() => {
    toast.classList.remove('show');
  }, 3000);
}

// ========== 配音选择 ==========
let selectedVoice = 'Xiaoyi';  // 默认晓伊
let currentAudio = null;

async function loadVoices() {
  try {
    const res = await fetch('/api/voices');
    const data = await res.json();
    const list = document.getElementById('voiceList');
    list.innerHTML = '';
    
    const keep = data.voices;
    
    keep.forEach(v => {
      const btn = document.createElement('button');
      const isLocal = v.type === 'local';
      const tag = isLocal ? '📴离线' : '☁️在线';
      const shortName = v.name.replace('mac_', '');
      btn.className = 'voice-btn' + (v.name.includes('Xiaoyi') ? ' active' : '');
      btn.dataset.url = v.url;
      btn.dataset.voice = v.name;
      btn.innerHTML = `<span class="play-icon">▶</span> ${shortName} <span style="opacity:0.5;font-size:10px;">${tag}</span>`;
      
      btn.onclick = () => {
        // 试听
        if (currentAudio) { currentAudio.pause(); currentAudio = null; }
        const audio = new Audio(v.url);
        audio.play().then(() => {
          console.log('playing:', v.url);
        }).catch(e => {
          console.log('play error', e);
          showToast('播放失败：' + e.message, 'error');
        });
        currentAudio = audio;
        
        // 选中
        document.querySelectorAll('.voice-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedVoice = v.name;
        showToast(`已选：${v.name}`);
      };
      
      list.appendChild(btn);
    });
  } catch (e) {
    console.log('loadVoices error', e);
  }
}

// ========== 环境检查 ==========
async function checkEnv() {
  try {
    const res = await fetch('/api/check-env');
    const data = await res.json();
    
    // Ollama
    const ollamaOk = data.ollama && data.ollama.ok;
    setEnvDot('ollama', ollamaOk, data.ollama ? data.ollama.status_text : '未安装');
    
    // Model
    const modelOk = data.model && data.model.ok;
    setEnvDot('model', modelOk, data.model ? (data.model.current || data.model.status_text) : '未下载');
    
    // FFmpeg
    const ffmpegOk = data.ffmpeg && data.ffmpeg.ok;
    setEnvDot('ffmpeg', ffmpegOk, data.ffmpeg ? data.ffmpeg.status_text : '未安装');
    
  } catch (e) {
    console.error('checkEnv error', e);
    setEnvDot('ollama', false, '错误');
    setEnvDot('model', false, '错误');
    setEnvDot('ffmpeg', false, '错误');
  }
}

function setEnvDot(name, ok, text) {
  const dot = document.getElementById('dot-' + name);
  const status = document.getElementById('status-' + name);
  dot.className = 'env-dot ' + (ok ? 'ok' : 'err');
  status.textContent = text;
}

// ========== 绑定事件 ==========
function bindEvents() {
  // 上传按钮
  document.getElementById('uploadBtn').addEventListener('click', () => {
    document.getElementById('fileInput').click();
  });
  
  // 文件选择
  document.getElementById('fileInput').addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      uploadFile(e.target.files[0]);
    }
  });
  
  // 拖拽上传
  document.body.addEventListener('dragover', (e) => {
    e.preventDefault();
  });
  document.body.addEventListener('drop', (e) => {
    e.preventDefault();
    if (e.dataTransfer.files.length > 0) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });
  
  // 生成按钮
  document.getElementById('generateBtn').addEventListener('click', () => {
    startGenerate();
  });
  
  // 聊天发送
  document.getElementById('chatSend').addEventListener('click', sendChat);
  document.getElementById('chatInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendChat();
  });
  
  // 打开文件夹
  document.getElementById('openFolderBtn').addEventListener('click', openFolder);
  
  // 关闭视频
  document.getElementById('closeVideoBtn').addEventListener('click', closeVideo);
}

// ========== 上传文件 ==========
async function uploadFile(file) {
  showToast('正在上传: ' + file.name, 'info');
  
  const formData = new FormData();
  formData.append('file', file);
  
  try {
    const res = await fetch('/api/upload', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    
    if (data.ok) {
      showToast('上传成功', 'success');
      state.docLoaded = true;
      state.filePath = data.path;  // 存文件路径
      
      // 启用聊天
      document.getElementById('chatInput').disabled = false;
      document.getElementById('chatSend').disabled = false;
      document.getElementById('generateBtn').disabled = false;
      
      // 显示目录
      renderChapters(data.chapters || []);
      
      // 加一条 AI 消息
      addChatMsg('ai', '文档已加载，你可以直接问我这本书讲了什么～');
      
    } else {
      showToast('上传失败: ' + (data.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('上传失败: ' + e.message, 'error');
  }
}

// ========== 渲染目录 ==========
function renderChapters(chapters) {
  const list = document.getElementById('chapterList');
  list.innerHTML = '';
  
  if (chapters.length === 0) {
    list.innerHTML = '<div class="empty-hint">未检测到章节，将生成全书总览</div>';
    return;
  }
  
  chapters.forEach((ch, i) => {
    const item = document.createElement('div');
    item.className = 'chapter-item';
    item.textContent = ch.title || ch;
    item.addEventListener('click', () => {
      item.classList.toggle('selected');
      if (item.classList.contains('selected')) {
        state.selectedChapters.add(i);
      } else {
        state.selectedChapters.delete(i);
      }
    });
    list.appendChild(item);
  });
}

// ========== 开始生成 ==========
async function startGenerate() {
  if (state.generating) {
    showToast('正在生成中，请稍候', 'info');
    return;
  }
  
  state.generating = true;
  document.getElementById('generateBtn').disabled = true;
  
  // 显示进度条
  document.getElementById('progressCard').style.display = 'block';
  
  try {
    const res = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: state.filePath,
        chapters: Array.from(state.selectedChapters)
      })
    });
    const data = await res.json();
    
    if (data.ok) {
      state.jobId = data.job_id;
      showToast('开始生成视频', 'success');
      startProgressPoll();
    } else {
      showToast('启动失败: ' + (data.error || ''), 'error');
      state.generating = false;
      document.getElementById('generateBtn').disabled = false;
    }
  } catch (e) {
    showToast('启动失败: ' + e.message, 'error');
    state.generating = false;
    document.getElementById('generateBtn').disabled = false;
  }
}

// ========== 进度轮询 ==========
function startProgressPoll() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  
  state.pollTimer = setInterval(async () => {
    try {
      const res = await fetch('/api/status?job_id=' + state.jobId);
      const data = await res.json();
      
      document.getElementById('progressLabel').textContent = data.message || '处理中...';
      document.getElementById('progressFill').style.width = (data.progress || 0) + '%';
      // 显示 ETA
      let etaText = '';
      if (data.elapsed !== undefined && data.eta !== undefined) {
        const e = Math.round(data.elapsed);
        const r = Math.round(data.eta);
        if (r > 0) {
          etaText = e + 's / 剩 ' + r + 's';
        } else {
          etaText = e + 's / 即将完成';
        }
      }
      const etaEl = document.getElementById('progressEta');
      if (etaEl) etaEl.textContent = etaText;
      
      if (data.done) {
        clearInterval(state.pollTimer);
        state.generating = false;
        document.getElementById('generateBtn').disabled = false;
        showToast('视频生成完成！', 'success');
        
        // 自动播放
        if (data.results && data.results.length > 0) {
          playVideo(data.results[0].url);
        }
        
        // 刷新历史
        loadHistory();
      }
      
      if (data.error) {
        clearInterval(state.pollTimer);
        state.generating = false;
        document.getElementById('generateBtn').disabled = false;
        showToast('生成失败: ' + data.error, 'error');
      }
    } catch (e) {
      console.error('progress poll error', e);
    }
  }, 1000);
}

// ========== 视频播放 ==========
function playVideo(url) {
  const player = document.getElementById('videoPlayer');
  const placeholder = document.getElementById('videoPlaceholder');
  const closeBtn = document.getElementById('closeVideoBtn');
  const downloadBtn = document.getElementById('downloadBtn');
  
  player.src = url;
  player.style.display = 'block';
  placeholder.style.display = 'none';
  closeBtn.style.display = 'block';
  downloadBtn.style.display = 'block';
  
  player.play().catch(e => console.log('play error', e));
  state.currentVideo = url;
}

function closeVideo() {
  const player = document.getElementById('videoPlayer');
  const placeholder = document.getElementById('videoPlaceholder');
  const closeBtn = document.getElementById('closeVideoBtn');
  const downloadBtn = document.getElementById('downloadBtn');
  
  player.pause();
  player.src = '';
  player.style.display = 'none';
  placeholder.style.display = 'block';
  closeBtn.style.display = 'none';
  downloadBtn.style.display = 'none';
  state.currentVideo = null;
}

// ========== 历史列表 ==========
async function loadHistory() {
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    const list = document.getElementById('historyList');
    
    if (!data.videos || data.videos.length === 0) {
      list.innerHTML = '<div class="empty-hint">还没有生成过视频，上传文件试试吧～</div>';
      return;
    }
    
    list.innerHTML = '';
    data.videos.forEach(v => {
      const item = document.createElement('div');
      item.className = 'history-item';
      const dur = v.duration ? v.duration + 's' : '';
      const size = v.size_kb ? v.size_kb + 'KB' : '';
      item.innerHTML = `
        <span class="history-name">${v.name}</span>
        <span class="history-meta">${dur} · ${size}</span>
        <span class="history-play">▶</span>
      `;
      item.addEventListener('click', () => {
        playVideo(v.url);
      });
      list.appendChild(item);
    });
  } catch (e) {
    console.error('loadHistory error', e);
  }
}

// ========== 打开文件夹 ==========
async function openFolder() {
  try {
    await fetch('/api/open-folder');
    showToast('已打开输出文件夹', 'success');
  } catch (e) {
    showToast('打开失败: ' + e.message, 'error');
  }
}

// ========== 聊天（流式） ==========
async function sendChat() {
  const input = document.getElementById('chatInput');
  const msg = input.value.trim();
  if (!msg) return;
  
  addChatMsg('user', msg);
  input.value = '';
  
  // 意图识别：说做视频就触发生成
  if (/视频|做成|生成|转成/.test(msg)) {
    addChatMsg('ai', '好的，我来帮你生成视频～');
    startGenerate();
    return;
  }
  
  // 创建空的 AI 消息框，边接收边填
  const aiMsgId = addChatMsg('ai', '');
  const aiMsgEl = document.getElementById(aiMsgId);
  let fullText = '';
  
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg })
    });
    
    // 读流式响应
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      
      // 按行解析 SSE
      const lines = buffer.split('\n');
      buffer = lines.pop();  // 最后一行可能不完整
      
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const jsonStr = line.slice(6);
        try {
          const data = JSON.parse(jsonStr);
          
          if (data.type === 'content') {
            fullText += data.text;
            aiMsgEl.textContent = fullText;
            // 自动滚动到底部
            const container = document.getElementById('chatMessages');
            container.scrollTop = container.scrollHeight;
          }
          else if (data.type === 'metrics') {
            // 追加指标面板
            const metricsHtml = `
              <div class="metrics-panel" style="margin-top:8px;">
                <div class="metric-item">
                  <span class="metric-label">耗时</span>
                  <span class="metric-value">${data.total_time}s</span>
                </div>
                <div class="metric-item">
                  <span class="metric-label">TPS</span>
                  <span class="metric-value">${data.tps}</span>
                </div>
                <div class="metric-item">
                  <span class="metric-label">tokens</span>
                  <span class="metric-value">${data.tokens}</span>
                </div>
              </div>
            `;
            aiMsgEl.innerHTML = fullText + metricsHtml;
          }
          else if (data.type === 'error') {
            aiMsgEl.textContent = '出错了: ' + data.message;
          }
        } catch (e) {
          console.log('parse error', e, jsonStr);
        }
      }
    }
    
  } catch (e) {
    aiMsgEl.textContent = '出错了，请稍后再试。';
  }
}

let chatMsgId = 0;
function addChatMsg(type, text) {
  const container = document.getElementById('chatMessages');
  const msg = document.createElement('div');
  msg.className = 'chat-msg ' + type;
  msg.textContent = text;
  msg.id = 'chat-msg-' + (++chatMsgId);
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;
  
  // 存到历史
  state.chatHistory.push({ type, text });
  saveChatToStorage();
  return msg.id;
}

function quickAsk(question) {
  document.getElementById('chatInput').value = question;
  sendChat();
}

// ========== localStorage 持久化 ==========
function saveChatToStorage() {
  try {
    localStorage.setItem('b2v_chat', JSON.stringify(state.chatHistory));
  } catch (e) {}
}

function loadChatFromStorage() {
  try {
    const saved = localStorage.getItem('b2v_chat');
    if (saved) {
      state.chatHistory = JSON.parse(saved);
      const container = document.getElementById('chatMessages');
      container.innerHTML = '';
      state.chatHistory.forEach(msg => {
        addChatMsg(msg.type, msg.text);
      });
    }
  } catch (e) {}
}
