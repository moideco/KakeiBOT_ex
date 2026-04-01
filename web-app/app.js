const KEY_WEBHOOK    = 'kakei_webhook_url';
const KEY_CATEGORIES = 'kakei_categories';
const KEY_CURRENCY   = 'kakei_currency';
const DEFAULT_CATS   = '食費,家賃,娯楽';

let displayString    = '0';
let selectedCategory = null;
let selectedCurrency = 'JPY';

// ── Init ──────────────────────────────────────────────

function init() {
  selectedCurrency = localStorage.getItem(KEY_CURRENCY) || 'JPY';
  document.getElementById('currencyLabel').textContent = selectedCurrency === 'JPY' ? '¥ JPY' : '$ USD';
  loadCategories();
  setupKeyboard();
}

// ── Categories ────────────────────────────────────────

function loadCategories() {
  const saved = localStorage.getItem(KEY_CATEGORIES) || DEFAULT_CATS;
  const cats  = saved.split(',').map(c => c.trim()).filter(Boolean);

  const section = document.getElementById('categorySection');
  section.innerHTML = '';
  selectedCategory  = null;
  updateCategoryDisplay();

  cats.forEach(cat => {
    const btn = document.createElement('button');
    btn.className   = 'category-chip';
    btn.textContent = cat;
    btn.onclick = () => toggleCategory(cat, btn);
    section.appendChild(btn);
  });
}

function toggleCategory(cat, btn) {
  if (selectedCategory === cat) {
    selectedCategory = null;
    btn.classList.remove('selected');
  } else {
    document.querySelectorAll('.category-chip').forEach(b => b.classList.remove('selected'));
    selectedCategory = cat;
    btn.classList.add('selected');
  }
  updateCategoryDisplay();
}

function updateCategoryDisplay() {
  document.getElementById('categoryDisplay').textContent = selectedCategory ?? 'カテゴリなし';
}

// ── Numpad logic ──────────────────────────────────────

function appendDigit(digit) {
  const isNeg = displayString.startsWith('-');
  const abs   = displayString.replace(/^-/, '');
  if (abs === '0') {
    displayString = isNeg ? '-' + digit : digit;
  } else {
    if (abs.replace('.', '').length >= 10) return;
    displayString += digit;
  }
  updateDisplay();
}

function appendDecimal() {
  if (displayString.includes('.')) return;
  displayString = (displayString === '0') ? '0.' : displayString + '.';
  updateDisplay();
}

function backspace() {
  if (displayString.length <= 1) {
    displayString = '0';
  } else {
    const r = displayString.slice(0, -1);
    displayString = (r === '-' || r === '') ? '0' : r;
  }
  updateDisplay();
}

function clearDisplay() {
  displayString = '0';
  updateDisplay();
}

function toggleSign() {
  if (displayString === '0') return;
  displayString = displayString.startsWith('-')
    ? displayString.slice(1)
    : '-' + displayString;
  updateDisplay();
}

function updateDisplay() {
  document.getElementById('amountDisplay').textContent = displayString;
}

// ── Send ──────────────────────────────────────────────

async function send() {
  const amount = parseFloat(displayString);
  if (!amount) {
    alert('金額を入力してください');
    return;
  }

  const webhookUrl = localStorage.getItem(KEY_WEBHOOK);
  if (!webhookUrl) {
    if (confirm('Webhook URL が設定されていません。設定画面を開きますか？')) {
      location.href = 'settings.html';
    }
    return;
  }

  // カテゴリなし → "<金額> <通貨>"  (Bot 側で食費扱い)
  // カテゴリあり → "<金額> <カテゴリ> <通貨>"
  const parts = [displayString, selectedCategory, selectedCurrency].filter(Boolean);
  const message = parts.join(' ');

  const sendBtn = document.getElementById('btnSend');
  sendBtn.disabled    = true;
  sendBtn.textContent = '...';

  try {
    const res = await fetch(webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: message }),
    });

    if (res.ok) {
      clearDisplay();
      document.querySelectorAll('.category-chip').forEach(b => b.classList.remove('selected'));
      selectedCategory = null;
      updateCategoryDisplay();
    } else {
      alert(`送信に失敗しました (${res.status})`);
    }
  } catch (e) {
    alert('送信に失敗しました: ' + e.message);
  } finally {
    sendBtn.disabled    = false;
    sendBtn.textContent = '送信';
  }
}

// ── Keyboard support (PC) ─────────────────────────────

function setupKeyboard() {
  document.addEventListener('keydown', e => {
    if (e.key >= '0' && e.key <= '9') { appendDigit(e.key); return; }
    switch (e.key) {
      case '.': case ',':  appendDecimal(); break;
      case 'Backspace':    backspace();     break;
      case 'Delete':
      case 'Escape':       clearDisplay();  break;
      case 'Enter':        send();          break;
    }
  });
}

init();
