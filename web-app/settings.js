const KEY_WEBHOOK    = 'kakei_webhook_url';
const KEY_CATEGORIES = 'kakei_categories';
const KEY_CURRENCY   = 'kakei_currency';
const DEFAULT_CATS   = '食費,家賃,娯楽';

let currentCategories = [];
let selectedCurrency  = 'JPY';

// ── Init ──────────────────────────────────────────────

function init() {
  document.getElementById('webhookInput').value =
    localStorage.getItem(KEY_WEBHOOK) || '';

  selectedCurrency = localStorage.getItem(KEY_CURRENCY) || 'JPY';
  updateCurrencyButtons();

  const saved = localStorage.getItem(KEY_CATEGORIES) || DEFAULT_CATS;
  currentCategories = saved.split(',').map(c => c.trim()).filter(Boolean);
  renderChips();

  document.getElementById('newCategoryInput')
    .addEventListener('keydown', e => { if (e.key === 'Enter') addCategory(); });
}

// ── Currency ──────────────────────────────────────────

function setCurrency(currency) {
  selectedCurrency = currency;
  updateCurrencyButtons();
}

function updateCurrencyButtons() {
  document.getElementById('btnJpy').classList.toggle('active', selectedCurrency === 'JPY');
  document.getElementById('btnUsd').classList.toggle('active', selectedCurrency === 'USD');
}

// ── Category management ───────────────────────────────

function renderChips() {
  const container = document.getElementById('categoriesChips');
  container.innerHTML = '';
  currentCategories.forEach((cat, i) => {
    const chip = document.createElement('div');
    chip.className = 'chip-edit';
    chip.innerHTML = `<span>${escapeHtml(cat)}</span>
                      <button onclick="removeCategory(${i})" title="削除">✕</button>`;
    container.appendChild(chip);
  });
}

function addCategory() {
  const input = document.getElementById('newCategoryInput');
  const name  = input.value.trim();
  if (!name) { alert('カテゴリ名を入力してください'); return; }
  if (currentCategories.includes(name)) { alert(`「${name}」はすでに登録されています`); return; }
  currentCategories.push(name);
  input.value = '';
  renderChips();
}

function removeCategory(index) {
  currentCategories.splice(index, 1);
  renderChips();
}

// ── Save ──────────────────────────────────────────────

function saveSettings() {
  const webhookUrl = document.getElementById('webhookInput').value.trim();
  if (webhookUrl && !webhookUrl.startsWith('https://discord.com/api/webhooks/')) {
    alert('Webhook URL の形式が正しくありません\n\n正しい形式: https://discord.com/api/webhooks/...');
    return;
  }
  try {
    localStorage.setItem(KEY_WEBHOOK,    webhookUrl);
    localStorage.setItem(KEY_CATEGORIES, currentCategories.join(','));
    localStorage.setItem(KEY_CURRENCY,   selectedCurrency);
  } catch (e) {
    alert('保存に失敗しました。\nブラウザの設定でローカルストレージが無効になっている可能性があります。\n\n詳細: ' + e.message);
    return;
  }
  // 保存確認
  const saved = localStorage.getItem(KEY_WEBHOOK);
  if (saved !== webhookUrl) {
    alert('保存の確認ができませんでした。ブラウザの設定を確認してください。');
    return;
  }
  location.href = 'index.html';
}

// ── Util ──────────────────────────────────────────────

function escapeHtml(str) {
  return str.replace(/[&<>"']/g, c =>
    ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

init();
