/* ============================================================
   TalentFlow AI — logic giao diện demo
   Trace được vẽ tuần tự để người xem thấy Agent "suy nghĩ" từng bước.
   ============================================================ */

const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let MODE = 'agent';
let BUSY = false;
let AUTONOMOUS_GOAL = '';

/* ---------------- KHỞI TẠO ---------------- */
async function boot() {
  const res = await fetch('/api/state').then((r) => r.json());
  AUTONOMOUS_GOAL = res.autonomous_goal;

  $('cfgProvider').textContent = `${res.config.provider} · ${res.config.model}`;
  $('cfgMax').textContent = res.config.max_iterations;
  $('guardMax').textContent = res.config.max_iterations;

  renderState(res.state);
  renderSamples(res.samples);
}

/* ---------------- BẢNG ATS ---------------- */
function renderState(state) {
  const bookedIds = new Set((state.booked || []).map((b) => b.candidate_id));

  $('jobList').innerHTML = state.jobs.map((j) => `
    <div class="job">
      <div class="job-id">${esc(j.id)}</div>
      <div class="job-title">${esc(j.title)}</div>
      <div class="job-skills">
        ${j.skills.map((s) => `<span class="skill">${esc(s)}</span>`).join('')}
        <span class="skill">≥ ${j.min_years} năm</span>
      </div>
    </div>`).join('');

  $('candidateList').innerHTML = state.candidates.map((c) => {
    const pass = c.score >= state.threshold;
    const isBooked = bookedIds.has(c.id);
    return `
      <div class="cand ${pass ? 'pass' : 'fail'} ${isBooked ? 'booked' : ''}">
        <div class="cand-top">
          <div>
            <div class="cand-name">${esc(c.name)}</div>
            <div class="cand-id">${esc(c.id)} · ${esc(c.job_id)}</div>
          </div>
          <div class="cand-score">${c.score}</div>
        </div>
        <div class="bar"><span style="width:${c.score}%"></span></div>
        <div class="cand-meta">
          <span>${esc(c.experience)}</span>
          <span>${esc(c.skills.slice(0, 3).join(', '))}</span>
        </div>
        ${c.tainted ? '<span class="tainted">⚠️ CV chứa nội dung thao túng</span>' : ''}
        ${isBooked ? '<span class="badge-booked">✅ Đã xếp lịch phỏng vấn</span>' : ''}
      </div>`;
  }).join('');

  $('slotGrid').innerHTML = Object.entries(state.slots).map(([date, times]) => `
    <div class="slot-day">
      <div class="slot-date">${esc(date)}</div>
      <div class="slot-times">
        ${Object.entries(times).map(([t, free]) =>
          `<span class="slot ${free ? 'free' : 'busy'}">${esc(t)}</span>`).join('')}
      </div>
    </div>`).join('');

  $('bookedList').innerHTML = (state.booked || []).map((b) =>
    `<div class="booked-row">📅 ${esc(b.candidate_id)} → ${esc(b.slot)}</div>`).join('');
}

/* ---------------- CHIP CÂU HỎI MẪU ---------------- */
function renderSamples(samples) {
  const box = $('sampleChips');
  box.innerHTML = '';
  samples.forEach((s) => {
    const b = el('button', `chip-q ${s.kind === 'attack' ? 'attack' : ''}`,
      `${s.tag} — ${esc(s.text.length > 52 ? s.text.slice(0, 52) + '…' : s.text)}`);
    b.title = s.text;
    b.onclick = () => { $('question').value = s.text; run(); };
    box.appendChild(b);
  });
}

/* ---------------- CHỌN CHẾ ĐỘ ---------------- */
document.querySelectorAll('.mode').forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll('.mode').forEach((b) => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    MODE = btn.dataset.mode;
    const q = $('question');
    if (MODE === 'autonomous') {
      q.value = AUTONOMOUS_GOAL;
      q.placeholder = 'Nhập MỤC TIÊU dài hạn cho Agent tự chủ…';
    } else {
      if (q.value === AUTONOMOUS_GOAL) q.value = '';
      q.placeholder = 'Nhập câu hỏi cho trợ lý tuyển dụng…';
    }
  };
});

/* ---------------- CHẠY ---------------- */
$('btnRun').onclick = run;
$('question').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) run();
});

$('btnReset').onclick = async () => {
  const r = await fetch('/api/reset', { method: 'POST', body: '{}' }).then((x) => x.json());
  renderState(r.state);
  $('output').innerHTML = '';
  $('statBar').hidden = true;
};

async function run() {
  if (BUSY) return;
  const question = $('question').value.trim();
  if (!question && MODE !== 'autonomous') { $('question').focus(); return; }

  BUSY = true;
  $('btnRun').disabled = true;
  $('overlay').hidden = false;
  $('overlayText').textContent =
    MODE === 'chatbot' ? 'Chatbot đang trả lời…'
      : MODE === 'agent' ? 'Agent đang suy luận Thought → Action → Observation…'
        : 'Agent tự chủ đang lập kế hoạch và thực thi…';
  $('output').innerHTML = '';
  $('statBar').hidden = true;

  // Đồng hồ đếm giây: Cấp 4 có thể chạy vài phút, không có phản hồi thì
  // người xem tưởng giao diện bị treo.
  const t0 = performance.now();
  const hint = $('overlayHint');
  const timer = setInterval(() => {
    const s = Math.round((performance.now() - t0) / 1000);
    hint.textContent = `Đã chạy ${s}s · mỗi bước là một lần gọi LLM thật`
      + (MODE === 'autonomous' ? ' · Cấp 4 thường mất 1–3 phút' : '');
  }, 500);

  let data;
  try {
    data = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: MODE, question }),
    }).then((r) => r.json());
  } catch (err) {
    data = { error: `Không gọi được server: ${err}. Kiểm tra cửa sổ terminal đang chạy python src/web_demo.py.` };
  }
  clearInterval(timer);
  hint.textContent = 'Mỗi bước là một lần gọi LLM thật, vui lòng đợi';
  const seconds = ((performance.now() - t0) / 1000).toFixed(1);

  $('overlay').hidden = true;
  $('btnRun').disabled = false;
  BUSY = false;

  if (data.error) {
    $('output').appendChild(stepCard('error', '❌ Lỗi', data.error));
    return;
  }

  if (data.state) renderState(data.state);
  await renderResult(data, seconds);
}

/* ---------------- VẼ KẾT QUẢ ---------------- */
function stepCard(kind, label, body, n) {
  const card = el('div', `step ${kind}`);
  const head = el('div', 'step-head');
  if (n != null) head.appendChild(el('span', 'step-n', `#${n}`));
  head.appendChild(el('span', null, label));
  card.appendChild(head);
  card.appendChild(el('div', 'step-body', esc(body)));
  return card;
}

async function push(node, delay = 260) {
  $('output').appendChild(node);
  node.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  await sleep(delay);
}

async function renderTrace(trace) {
  for (const e of trace) {
    if (e.thought) await push(stepCard('thought', '🧠 Thought', e.thought, e.step));
    if (e.action) await push(stepCard(
      e.action.startsWith('book_interview') ? 'action write' : 'action',
      e.action.startsWith('book_interview') ? '🔐 Action — HÀNH ĐỘNG GHI' : '🛠️ Action',
      e.action, e.step));
    if (e.observation) {
      const isErr = e.observation.startsWith('LỖI:');
      await push(stepCard(`obs ${isErr ? 'err' : ''}`,
        isErr ? '⚠️ Observation — lỗi nghiệp vụ' : '👁️ Observation', e.observation, e.step));
    }
    if (e.pending_final) {
      await push(stepCard('confirm', '🛡️ Guardrail G4 — dừng xin xác nhận', e.pending_final, e.step));
      await push(stepCard('confirm', '👤 Người dùng', 'Tôi xác nhận, hãy tiến hành đặt lịch.'));
    }
  }
}

async function renderResult(data, seconds) {
  const out = $('output');

  /* ---- CẤP 4: Autonomous ---- */
  if (data.mode === 'autonomous') {
    const plan = el('div', 'step plan');
    plan.appendChild(el('div', 'step-head', '<span>📋 Pha 1 — Planning · Agent tự chia nhỏ mục tiêu</span>'));
    const list = el('div', 'plan-steps');
    (data.plan || []).forEach((s, i) =>
      list.appendChild(el('div', 'plan-step', `<b>${i + 1}.</b>${esc(s)}`)));
    plan.appendChild(list);
    await push(plan, 420);

    for (const c of data.cycles || []) {
      await push(el('div', 'step cycle', `⚙️ Pha 2 — Chu kỳ ${c.cycle} · ${esc(c.step)}`), 220);
      await renderTrace(c.trace || []);
      if (c.verdict) {
        const done = c.verdict.toUpperCase().startsWith('HOÀN THÀNH');
        await push(stepCard(done ? 'final' : 'guard',
          done ? '🔎 Pha 3 — Reflection · mục tiêu đã đạt' : '🔎 Pha 3 — Reflection · tiếp tục',
          c.verdict));
      }
    }

    if ((data.bookings || []).length) {
      await push(stepCard('final', '📅 Trạng thái thật — lịch đã đặt',
        data.bookings.map((b) => `${b.candidate_id} → ${b.slot}`).join('\n')));
    }
    setStats({ steps: data.steps, tools: data.tool_calls, guard: false,
      wrote: (data.bookings || []).length > 0, seconds });
    return;
  }

  /* ---- CẤP 2 & 3 ---- */
  if (data.mode === 'chatbot') {
    await push(stepCard('obs', '💬 Chatbot Cấp 2 — không có công cụ',
      'Không gọi tool nào. Trả lời hoàn toàn bằng kiến thức sẵn có của mô hình.'), 200);
  } else {
    await renderTrace(data.trace || []);
  }

  if (data.stopped_by_guardrail) {
    await push(stepCard('guard', '🛡️ Guardrail — đã chạm giới hạn vòng lặp',
      'Agent dừng an toàn, không thực hiện thao tác nào chưa chắc chắn.'));
  }

  await push(stepCard('final', '🏁 Final Answer', data.final_answer || '(trống)'));

  const wrote = (data.trace || []).some(
    (e) => e.action && e.action.startsWith('book_interview') &&
           e.observation && !e.observation.startsWith('LỖI:'));
  setStats({ steps: data.steps, tools: data.tool_calls,
    guard: data.stopped_by_guardrail, wrote, seconds });
}

function setStats({ steps, tools, guard, wrote, seconds }) {
  $('statBar').hidden = false;
  $('stSteps').textContent = steps ?? '–';
  $('stTools').textContent = tools ?? 0;

  const g = $('stGuard');
  g.textContent = guard ? 'ĐÃ NGẮT' : 'không cần';
  g.className = guard ? 'warn' : 'good';

  const w = $('stWrite');
  w.textContent = wrote ? 'CÓ' : 'không';
  w.className = wrote ? 'warn' : 'good';

  $('stTime').textContent = `${seconds}s`;
}

boot();
