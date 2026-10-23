/* Evidence belongs to one exact product. Viewing never executes generated code. */
(() => {
  const $ = (s) => document.querySelector(s);
  const panel = document.createElement("section");
  panel.id = "product-quality";
  panel.className = "quality-panel";
  panel.hidden = true;
  panel.innerHTML = `<div class="section-heading"><h3>Chất lượng bộ tệp</h3><button id="quality-refresh" class="secondary">Kiểm tra lại</button></div>
    <p id="quality-summary" role="status"></p>
    <div class="quality-layers"><p id="quality-completeness"></p><p id="quality-syntax"></p><p id="quality-execution"></p></div>
    <p id="quality-ai" class="hint"></p><p id="quality-scope" class="hint"></p><ul id="quality-issues"></ul>
    <details><summary>Danh sách tệp và dấu kiểm chứng</summary><ul id="quality-files"></ul><p id="quality-digest" class="hint"></p></details>
    <div class="action-row"><button id="repair-missing" class="secondary" hidden>Nhờ bot bổ sung tệp thiếu</button><a id="quality-download" hidden>Tải bằng chứng (.json) ↓</a></div>`;
  $("#inspector-status").after(panel);
  let task = null,
    signature = "",
    report = null,
    url = null,
    sequence = 0;
  const labels = {
    passed: "Đạt trong phạm vi đã kiểm tra",
    failed: "Chưa đạt",
    not_run: "Chưa chạy",
    unavailable: "Chưa chạy được",
    not_supported: "Chưa hỗ trợ",
    unverified: "Chưa có danh sách để đối chiếu",
    demo: "Mô phỏng",
  };
  function clearDownload() {
    if (url) URL.revokeObjectURL(url);
    url = null;
    $("#quality-download").hidden = true;
  }
  async function load() {
    if (!task || panel.hidden) return;
    const id = task.id,
      turn = ++sequence;
    $("#quality-refresh").disabled = true;
    $("#quality-summary").textContent =
      "Đang đối chiếu bộ tệp; chỉ kiểm tra tĩnh ở bước này…";
    $("#repair-missing").hidden = true;
    clearDownload();
    try {
      const response = await apiFetch("/api/tasks/" + id + "/quality");
      const value = await response.json();
      if (!response.ok)
        throw Error(value.error || "Chưa đọc được kết quả kiểm tra");
      if (turn !== sequence || task?.id !== id) return;
      report = value;
      $("#quality-summary").textContent = {
        blocked: "Bộ tệp chưa đạt · xem các lỗi bên dưới.",
        tested_scope: "Đủ tệp và đã đạt các ca kiểm thử Docker được ghi nhận.",
        static_only: "Đủ tệp, đạt cú pháp · chưa kiểm thử chức năng.",
        needs_review: "Cần bạn xem · còn phạm vi chưa được xác minh.",
        demo: "Đây là bộ tệp mô phỏng.",
      }[value.status];
      $("#quality-completeness").textContent =
        "1 · Bộ tệp: " + (labels[value.completeness.status] || "Chưa xác định");
      $("#quality-syntax").textContent =
        `2 · Cú pháp: ${labels[value.syntax.status] || "Chưa xác định"} · ${value.syntax.checked || 0} tệp đã kiểm tra`;
      $("#quality-execution").textContent =
        `3 · Chức năng: ${labels[value.execution.status] || "Chưa xác định"} · ${value.execution.tests || 0} ca`;
      $("#quality-scope").textContent = value.scope;
      $("#quality-ai").textContent =
        "AI đánh giá: " +
        (value.ai_review.passed === true
          ? "Đạt (ý kiến của mô hình)"
          : value.ai_review.passed === false
            ? "Chưa đạt · xem lý do bên dưới"
            : "Chưa có kết luận hợp lệ");
      $("#quality-issues").replaceChildren();
      for (const message of [
        ...value.ai_review.issues,
        ...value.completeness.issues,
        ...value.syntax.findings
          .filter((f) => f.status === "failed")
          .map((f) => f.path + ": " + f.message),
        ...(value.execution.status === "failed"
          ? [value.execution.output]
          : []),
      ]) {
        const item = document.createElement("li");
        item.textContent = message;
        $("#quality-issues").append(item);
      }
      $("#quality-files").replaceChildren();
      for (const file of value.files) {
        const item = document.createElement("li");
        item.textContent = `${file.path} · ${{ present: "Có tệp", empty: "Rỗng", missing: "Thiếu" }[file.status]}${file.required ? " · bắt buộc" : ""} · ${file.bytes} byte`;
        $("#quality-files").append(item);
      }
      $("#quality-digest").textContent =
        "SHA-256 bộ tệp: " + value.content_sha256;
      $("#repair-missing").hidden =
        !value.missing_files.length || task.mode === "demo";
      url = URL.createObjectURL(
        new Blob([JSON.stringify(value, null, 2)], {
          type: "application/json;charset=utf-8",
        }),
      );
      $("#quality-download").href = url;
      $("#quality-download").download = "quality-" + id + ".json";
      $("#quality-download").hidden = false;
      $("#product-download-zip").textContent =
        value.status === "blocked"
          ? "Tải bộ tệp chưa đạt (ZIP) ↓"
          : "Tải bộ tệp ZIP ↓";
    } catch (error) {
      if (turn === sequence && task?.id === id)
        $("#quality-summary").textContent = error.message;
    } finally {
      if (turn === sequence) $("#quality-refresh").disabled = false;
    }
  }
  $("#quality-refresh").onclick = load;
  $("#repair-missing").onclick = async () => {
    if (task && report?.missing_files.length)
      await beginMissingRepair(task, report.missing_files);
  };
  window.addEventListener("workspace:task", ({ detail }) => {
    task = detail;
    panel.hidden =
      !detail.product || ["queued", "running"].includes(detail.status);
    const next = detail.id + ":" + detail.status;
    if (signature === next) return;
    signature = next;
    report = null;
    ++sequence;
    clearDownload();
    $("#quality-files").replaceChildren();
    $("#quality-issues").replaceChildren();
    for (const name of [
      "ai",
      "completeness",
      "syntax",
      "execution",
      "scope",
      "digest",
    ])
      $("#quality-" + name).textContent = "";
    if (!panel.hidden) load();
  });
  window.addEventListener("workspace:checks", ({ detail }) => {
    if (task?.id === detail.id) load();
  });
  window.addEventListener("workspace:closed", () => {
    ++sequence;
    task = null;
    signature = "";
    report = null;
    panel.hidden = true;
    clearDownload();
  });
})();
