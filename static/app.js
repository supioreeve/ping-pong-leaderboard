let currentSort = "wins";
let players = [];

async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function fmtTime(iso) {
  const d = new Date(iso.replace(" ", "T") + "Z");
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function renderLeaderboard(rows) {
  const el = document.getElementById("leaderboard");
  if (!rows.length) {
    el.innerHTML = '<p class="empty-state">No players yet.</p>';
    return;
  }
  const sorted = [...rows].sort((a, b) => {
    if (currentSort === "elo") return b.elo - a.elo;
    return b.wins - a.wins || b.elo - a.elo;
  });
  el.innerHTML = sorted
    .map((p, i) => {
      const badges = p.badges.map((b) => `<span title="${b.label}">${b.emoji}</span>`).join(" ");
      return `
        <div class="lb-row ${i === 0 ? "rank-1" : ""}">
          <div class="lb-rank">${i + 1}</div>
          <div class="lb-name">${p.name} <span class="lb-badges">${badges}</span></div>
          <div class="lb-record">${p.wins}-${p.losses}</div>
          <div class="lb-pct">${p.win_pct}%</div>
          <div class="lb-elo">${p.elo}</div>
        </div>
      `;
    })
    .join("");
}

function renderHistory(rows) {
  const el = document.getElementById("history");
  if (!rows.length) {
    el.innerHTML = '<p class="empty-state">No matches logged yet. Get playing!</p>';
    return;
  }
  el.innerHTML = rows
    .map(
      (m) => `
      <div class="history-item">
        <div class="hi-line">
          <span><span class="hi-winner">${m.winner}</span> beat ${m.loser}
            <small style="color:var(--text-muted)">(+${m.winner_elo_delta} / ${m.loser_elo_delta})</small>
          </span>
          <span class="hi-time">${fmtTime(m.created_at)}</span>
        </div>
        ${m.comment ? `<div class="hi-comment">"${escapeHtml(m.comment)}"</div>` : ""}
      </div>
    `
    )
    .join("");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function fillSelect(sel, names, placeholder) {
  sel.innerHTML =
    (placeholder ? `<option value="" disabled selected>${placeholder}</option>` : "") +
    names.map((n) => `<option value="${n}">${n}</option>`).join("");
}

async function refreshLeaderboard() {
  const rows = await api("/api/leaderboard");
  renderLeaderboard(rows);
}

async function refreshHistory() {
  const rows = await api("/api/matches");
  renderHistory(rows);
}

async function init() {
  players = await api("/api/players");
  fillSelect(document.getElementById("winner"), players, "Select winner");
  fillSelect(document.getElementById("loser"), players, "Select loser");
  fillSelect(document.getElementById("h2h-a"), players);
  fillSelect(document.getElementById("h2h-b"), players);
  document.getElementById("h2h-b").selectedIndex = 1;

  await Promise.all([refreshLeaderboard(), refreshHistory()]);

  document.querySelectorAll(".toggle-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".toggle-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentSort = btn.dataset.sort;
      refreshLeaderboard();
    });
  });

  document.getElementById("match-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errorEl = document.getElementById("form-error");
    errorEl.textContent = "";
    const winner = document.getElementById("winner").value;
    const loser = document.getElementById("loser").value;
    const comment = document.getElementById("comment").value;

    if (winner === loser) {
      errorEl.textContent = "Winner and loser must be different people.";
      return;
    }

    try {
      await api("/api/matches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ winner, loser, comment }),
      });
      document.getElementById("comment").value = "";
      await Promise.all([refreshLeaderboard(), refreshHistory()]);
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });

  document.getElementById("h2h-btn").addEventListener("click", async () => {
    const a = document.getElementById("h2h-a").value;
    const b = document.getElementById("h2h-b").value;
    const resultEl = document.getElementById("h2h-result");
    if (a === b) {
      resultEl.innerHTML = '<p class="empty-state">Pick two different players.</p>';
      return;
    }
    try {
      const data = await api(`/api/head-to-head?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
      const recentHtml = data.recent.length
        ? data.recent
            .map(
              (m) =>
                `<div class="history-item"><div class="hi-line"><span><span class="hi-winner">${m.winner}</span> beat ${m.loser}</span><span class="hi-time">${fmtTime(m.created_at)}</span></div>${m.comment ? `<div class="hi-comment">"${escapeHtml(m.comment)}"</div>` : ""}</div>`
            )
            .join("")
        : '<p class="empty-state">No matches between these two yet.</p>';
      resultEl.innerHTML = `
        <div class="h2h-score">
          <div><span class="name">${data.a}</span>${data.a_wins}</div>
          <span>&mdash;</span>
          <div><span class="name">${data.b}</span>${data.b_wins}</div>
        </div>
        ${recentHtml}
      `;
    } catch (err) {
      resultEl.innerHTML = `<p class="empty-state">${err.message}</p>`;
    }
  });
}

init();
