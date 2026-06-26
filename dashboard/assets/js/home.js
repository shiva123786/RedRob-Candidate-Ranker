/**
 * home.js — populates the stats row and the "top of the shortlist" preview
 * table on index.html from the engine's JSON exports.
 */
(function () {
  function statCard(value, label) {
    return `<div class="stat"><div class="stat-value">${value}</div><div class="stat-label">${label}</div></div>`;
  }

  function renderStats(meta) {
    const row = document.getElementById("stats-row");
    row.innerHTML = [
      statCard(meta.total_candidates_processed.toLocaleString(), "candidates processed"),
      statCard(meta.honeypots_excluded, "honeypots excluded"),
      statCard(meta.elapsed_seconds + "s", "end-to-end runtime"),
      statCard(meta.top_n, "candidates shortlisted"),
    ].join("");

    const ts = document.getElementById("meta-timestamp");
    if (ts) ts.textContent = "generated " + meta.generated_at;
  }

  function scoreSignal(score) {
    const pct = Math.round(score * 100);
    return `
      <div class="signal">
        <div class="track"><div class="fill" style="width:${pct}%"></div></div>
        <div class="value">${score.toFixed(2)}</div>
      </div>`;
  }

  function renderPreview(results) {
    const wrap = document.getElementById("preview-table-wrap");
    const top5 = results.slice(0, 5);
    const rows = top5.map((r) => `
      <tr onclick="window.location.href='rankings.html'">
        <td class="rank-num">${r.rank}</td>
        <td class="name-cell">
          <div class="who">${r.anonymized_name}</div>
          <div class="role">${r.current_title} · ${r.current_company}</div>
        </td>
        <td class="score-cell">${scoreSignal(r.score)}</td>
      </tr>
    `).join("");

    wrap.innerHTML = `
      <table class="rank-table">
        <thead><tr><th></th><th>Candidate</th><th>Redrob score</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  async function init() {
    try {
      const [meta, results] = await Promise.all([
        RedrobData.loadMeta(),
        RedrobData.loadPreviousResults(),
      ]);
      renderStats(meta);
      renderPreview(results);
    } catch (err) {
      console.error(err);
      document.getElementById("stats-row").innerHTML =
        `<div class="stat"><div class="stat-value">—</div><div class="stat-label">Run with a local server (see README) so the dashboard can fetch data/*.json.</div></div>`;
    }
  }

  async function handleUpload() {
    const fileInput = document.getElementById("csv-upload");
    const modeInput = document.getElementById("ranking-mode");
    const status = document.getElementById("upload-status");
    if (!fileInput.files.length) {
      status.textContent = "Choose a CSV file first.";
      return;
    }
    status.textContent = "Ranking uploaded CSV…";
    try {
      const result = await RedrobData.uploadCsv(fileInput.files[0], modeInput.value);
      status.textContent = `Uploaded ${result.candidate_count} candidates using ${result.mode}.`;
      renderPreview(result.results || []);
    } catch (err) {
      console.error(err);
      status.textContent = "Upload failed. Make sure the local server is running.";
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    init();
    const button = document.getElementById("run-upload");
    if (button) button.addEventListener("click", handleUpload);
  });
})();
