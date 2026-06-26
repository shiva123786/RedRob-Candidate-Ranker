/**
 * rankings.js — drives rankings.html: renders the full top-100 table,
 * wires up search + filter chips, and expands a reasoning row per
 * candidate built straight from the engine's feature export.
 */
(function () {
  let ALL_RESULTS = [];
  let activeFilter = "all";
  let searchTerm = "";
  const expanded = new Set();

  function scoreSignal(score, dim) {
    const pct = Math.round(score * 100);
    return `
      <div class="signal">
        <div class="track"><div class="fill${dim ? " dim" : ""}" style="width:${pct}%"></div></div>
        <div class="value">${score.toFixed(2)}</div>
      </div>`;
  }

  function conceptTags(r) {
    const tags = [];
    r.matched_concepts.forEach((c) => tags.push(`<span class="tag good">${c}</span>`));
    r.nice_to_have_matched.forEach((c) => tags.push(`<span class="tag">${c}</span>`));
    r.fired_disqualifiers.forEach((c) => tags.push(`<span class="tag danger">${c.replace(/_/g, " ")}</span>`));
    if (r.notice_period_days > 60) tags.push(`<span class="tag danger">${r.notice_period_days}d notice</span>`);
    if (!r.open_to_work_flag) tags.push(`<span class="tag">not flagged open-to-work</span>`);
    return tags.join("");
  }

  function rowHtml(r) {
    const isOpen = expanded.has(r.candidate_id);
    return `
      <tr data-id="${r.candidate_id}" class="main-row">
        <td class="rank-num">${r.rank}</td>
        <td class="name-cell">
          <div class="who">${r.anonymized_name}</div>
          <div class="role">${r.current_title} · ${r.current_company} · ${r.location}</div>
        </td>
        <td class="score-cell">${scoreSignal(r.score, r.fired_disqualifiers.length > 0)}</td>
      </tr>
      <tr class="reasoning-row${isOpen ? "" : " hidden-row"}" data-id-detail="${r.candidate_id}">
        <td colspan="3">
          ${r.reasoning}
          <div class="tag-row">${conceptTags(r)}</div>
        </td>
      </tr>
    `;
  }

  function passesFilter(r) {
    if (activeFilter === "clean" && r.fired_disqualifiers.length > 0) return false;
    if (activeFilter === "flagged" && r.fired_disqualifiers.length === 0) return false;
    if (searchTerm) {
      const haystack = `${r.anonymized_name} ${r.current_title} ${r.current_company}`.toLowerCase();
      if (!haystack.includes(searchTerm)) return false;
    }
    return true;
  }

  function render() {
    const wrap = document.getElementById("table-wrap");
    const rows = ALL_RESULTS.filter(passesFilter);

    if (rows.length === 0) {
      wrap.innerHTML = `<div class="empty-state">No candidates match that filter.</div>`;
      return;
    }

    wrap.innerHTML = `
      <table class="rank-table">
        <thead><tr><th></th><th>Candidate</th><th>Redrob score</th></tr></thead>
        <tbody>${rows.map(rowHtml).join("")}</tbody>
      </table>
    `;

    wrap.querySelectorAll("tr.main-row").forEach((tr) => {
      tr.addEventListener("click", () => {
        const id = tr.dataset.id;
        if (expanded.has(id)) expanded.delete(id);
        else expanded.add(id);
        render();
      });
    });
  }

  function init() {
    document.getElementById("search-input").addEventListener("input", (e) => {
      searchTerm = e.target.value.trim().toLowerCase();
      render();
    });

    document.querySelectorAll(".filter-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        document.querySelectorAll(".filter-chip").forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        activeFilter = chip.dataset.filter;
        render();
      });
    });

    RedrobData.loadResults()
      .then((results) => {
        ALL_RESULTS = results;
        render();
      })
      .catch((err) => {
        console.error(err);
        document.getElementById("table-wrap").innerHTML =
          `<div class="empty-state">Couldn't load data/results.json — run this via the local server in README.md, not by double-clicking the file.</div>`;
      });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
