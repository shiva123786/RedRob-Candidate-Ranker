/**
 * data.js
 * Tiny shared loader for the two JSON files the engine produces:
 *   data/results.json   — the ranked top-100 with full feature breakdown
 *   data/run_meta.json  — pool size, honeypots excluded, run time
 * Both pages fetch through this module so there's one place that knows
 * the file paths and one place to change if the engine's export shape
 * changes.
 */
const RedrobData = (function () {
  async function loadResults() {
    const res = await fetch("data/results.json");
    if (!res.ok) throw new Error("Could not load data/results.json");
    return res.json();
  }

  async function loadMeta() {
    const res = await fetch("data/run_meta.json");
    if (!res.ok) throw new Error("Could not load data/run_meta.json");
    return res.json();
  }

  async function loadPreviousResults() {
    try {
      return await loadResults();
    } catch (err) {
      return [];
    }
  }

  async function uploadCsv(file, mode) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("mode", mode);
    const res = await fetch("/upload", {
      method: "POST",
      body: formData,
    });
    if (!res.ok) throw new Error("Upload failed");
    return res.json();
  }

  return { loadResults, loadMeta, uploadCsv };
})();
