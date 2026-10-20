const labels = {
  queued: "Chờ",
  running: "Đang làm",
  completed: "Đã chạy xong",
  failed: "Thất bại",
  interrupted: "Bị gián đoạn",
  needs_review: "Cần bạn xem",
  cancelled: "Đã hủy",
  approved: "Bạn đã duyệt",
};
function reviewText(text) {
  try {
    const value = JSON.parse(text);
    if (typeof value.passed === "boolean" && Array.isArray(value.issues))
      return (
        (value.passed
          ? "AI đánh giá: Đạt (chưa xác minh bên ngoài)"
          : "AI đánh giá: Chưa đạt") +
        (value.issues.length
          ? "\n" + value.issues.map((item) => "• " + item).join("\n")
          : "")
      );
  } catch {}
  return text;
}
function el(tag, text) {
  const n = document.createElement(tag);
  n.textContent = text;
  return n;
}
let sessionToken;
let budgetTouched = false;
let selectedDocuments = [];
let selectedProject = "default";
const expertNames = {
  planner: "ECC · Lập kế hoạch",
  architect: "ECC · Kiến trúc",
  python: "ECC · Python",
  web: "ECC · Web",
  data: "ECC · Dữ liệu JSON",
  none: "Đội cơ bản",
};
async function loadVersion() {
  const label = document.querySelector("#app-version");
  try {
    const response = await fetch("/api/version");
    if (!response.ok) throw Error();
    const info = await response.json();
    label.textContent =
      "Phiên bản " +
      info.version +
      " · commit " +
      info.commit.slice(0, 12) +
      (info.dirty_at_start ? " · Có thay đổi cục bộ lúc khởi động" : "") +
      " · Mã nguồn " +
      info.source_digest.slice(0, 12);
    label.title =
      "Khởi động: " + new Date(info.started_at).toLocaleString("vi-VN");
  } catch {
    label.textContent =
      "Chưa đọc được phiên bản máy chủ; hãy khởi động lại app và tải lại trang.";
  }
}
loadVersion();
async function apiFetch(url, options = {}) {
  if (options.method === "POST") {
    if (!sessionToken) {
      const response = await fetch("/api/session");
      if (!response.ok)
        throw Error("Không khởi tạo được phiên; hãy tải lại trang");
      sessionToken = (await response.json()).token;
    }
    options = {
      ...options,
      headers: {
        ...options.headers,
        "Content-Type": "application/json",
        "X-CSRF-Token": sessionToken,
      },
    };
  }
  return fetch(url, options);
}
async function viewFiles(id) {
  if (window.WorkspaceUI) return window.WorkspaceUI.openTask(id, "code");
  document.querySelector("#dialog-title").textContent = "Bộ tệp sản phẩm";
  try {
    const response = await apiFetch("/api/tasks/" + id + "/files");
    const data = await response.json();
    if (!response.ok) throw Error(data.error);
    const dialog = document.querySelector("#file-dialog"),
      list = document.querySelector("#file-list"),
      content = document.querySelector("#file-content");
    list.replaceChildren();
    content.textContent = "";
    document.querySelector("#file-notice").textContent =
      (data.mode === "demo" ? "MÔ PHỎNG. " : "") +
      "Mã chưa được chạy hoặc xác minh an toàn. Hãy đọc trước khi sử dụng. Trạng thái: " +
      (labels[data.status] || data.status);
    const download = document.querySelector("#download-file");
    download.hidden = false;
    function selectFile(index) {
      content.textContent = data.files[index].content;
      download.href = "/api/tasks/" + id + "/file/" + index;
      download.textContent = "Tải " + data.files[index].path;
    }
    data.files.forEach((file, index) => {
      const button = el("button", file.path);
      button.onclick = () => selectFile(index);
      list.append(button);
    });
    selectFile(0);
    dialog.showModal();
  } catch (e) {
    reportError(e.message);
  }
}
document.querySelector("#close-files").onclick = () =>
  document.querySelector("#file-dialog").close();
let pageOffset = 0,
  refreshVersion = 0;
let queuePaused = false,
  queueUpdating = false;
document.querySelector("#toggle-queue").onclick = async () => {
  queueUpdating = true;
  document.querySelector("#toggle-queue").disabled = true;
  try {
    const response = await apiFetch("/api/queue", {
      method: "POST",
      body: JSON.stringify({ paused: !queuePaused }),
    });
    if (!response.ok) throw Error("Chưa đổi được trạng thái hàng đợi");
    await refresh();
  } catch (e) {
    reportError(e.message);
  } finally {
    queueUpdating = false;
    document.querySelector("#toggle-queue").disabled = false;
  }
};
function duration(start, finish) {
  if (!start) return "Chưa bắt đầu";
  const seconds = Math.max(
    0,
    Math.floor(
      ((finish ? Date.parse(finish) : Date.now()) - Date.parse(start)) / 1000,
    ),
  );
  return seconds < 60
    ? seconds + " giây"
    : Math.floor(seconds / 60) + " phút " + (seconds % 60) + " giây";
}
function updateDurations() {
  document.querySelectorAll("[data-duration]").forEach((element) => {
    element.textContent =
      "Đã xong " +
      element.dataset.steps +
      " bước · " +
      duration(element.dataset.start, element.dataset.finish);
  });
}
async function viewHistory(id) {
  try {
    const response = await apiFetch("/api/tasks/" + id + "/history");
    const history = await response.json();
    if (!response.ok) throw Error(history.error);
    document.querySelector("#dialog-title").textContent = "Lịch sử từng bước";
    document.querySelector("#download-file").hidden = true;
    const list = document.querySelector("#file-list"),
      content = document.querySelector("#file-content");
    list.replaceChildren();
    document.querySelector("#file-notice").textContent =
      "Lưu kết quả từng lượt, kể cả trước khi sửa. Tổng thời gian: " +
      (history.timing
        ? duration(history.timing.started_at, history.timing.finished_at)
        : "Chưa có dữ liệu");
    const names = {
        supervise: "Chuyên gia ECC",
        plan: "Điều phối",
        result: "Thực hiện",
        review: "Kiểm tra",
      },
      states = {
        limited: "Hết lượt gọi",
        completed: "Xong",
        running: "Đang chạy",
        cancelled: "Đã hủy",
        failed: "Lỗi",
        interrupted: "Gián đoạn",
      };
    function describe(step) {
      return (
        names[step.role] +
        " · lượt " +
        step.attempt +
        " · " +
        (states[step.status] || step.status) +
        " · " +
        duration(step.started_at, step.finished_at) +
        "\n\n" +
        (step.cleared_at
          ? "Nội dung lượt này đã được dọn vào " +
            new Date(step.cleared_at).toLocaleString("vi-VN") +
            ". Kết quả cuối của nhiệm vụ vẫn được giữ."
          : step.output
            ? step.role === "review"
              ? reviewText(step.output)
              : step.output
            : "Chưa có kết quả cho bước này.")
      );
    }
    for (const step of history.steps) {
      const button = el(
        "button",
        (names[step.role] || step.role) +
          " " +
          step.attempt +
          " · " +
          (states[step.status] || step.status),
      );
      button.onclick = () => {
        content.textContent = describe(step);
      };
      list.append(button);
    }
    content.textContent = history.steps.length
      ? describe(history.steps[history.steps.length - 1])
      : "Chưa có lịch sử từng bước. Nhiệm vụ tạo ở bản cũ vẫn giữ kết quả cuối.";
    document.querySelector("#file-dialog").showModal();
  } catch (e) {
    reportError(e.message);
  }
}

async function checkHealth() {
  const button = document.querySelector("#check-health");
  button.disabled = true;
  const status = document.querySelector("#health-status");
  status.textContent = "Đang kiểm tra...";
  try {
    const response = await apiFetch("/api/health");
    if (!response.ok) throw Error("Không đọc được kết nối");
    const data = await response.json(),
      info = data.ollama;
    window.dispatchEvent(new CustomEvent("workspace:health", { detail: info }));
    status.textContent =
      info.status === "ready"
        ? "Ollama đang phản hồi · Đã có " + info.model
        : info.status === "model_missing"
          ? "Ollama đang chạy, nhưng chưa tìm thấy " +
            info.model +
            ". Hãy tải mô hình trong Ollama."
          : "Chưa kết nối được Ollama. Hãy mở ứng dụng Ollama rồi kiểm tra lại.";
  } catch (e) {
    status.textContent = e.message;
  } finally {
    button.disabled = false;
  }
}
document.querySelector("#check-health").onclick = checkHealth;
document.querySelector("#backup").onclick = async () => {
  if (
    !confirm(
      "Tải toàn bộ lịch sử, sản phẩm và bộ nhớ về máy? Bản sao có thể chứa thông tin riêng tư.",
    )
  )
    return;
  const button = document.querySelector("#backup"),
    status = document.querySelector("#backup-status");
  button.disabled = true;
  status.textContent = "Đang tạo bản sao nhất quán...";
  try {
    const response = await apiFetch("/api/backup", { method: "POST" });
    if (!response.ok) throw Error("Chưa tạo được bản sao lưu");
    const blob = await response.blob(),
      url = URL.createObjectURL(blob),
      link = el("a", "");
    link.href = url;
    link.download =
      "bao-mat-backup-" +
      new Date().toISOString().replace(/[:.]/g, "-") +
      ".zip";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    status.textContent =
      "Đã gửi bản sao lưu tới trình duyệt. Hãy kiểm tra thư mục tải xuống.";
  } catch (e) {
    status.textContent = e.message;
  } finally {
    button.disabled = false;
  }
};
let cleanupPreview = null,
  cleanupBusy = false;
function updateCleanupControls() {
  document.querySelector("#apply-cleanup").disabled =
    cleanupBusy ||
    !cleanupPreview?.items ||
    document.querySelector("#cleanup-confirmation").value !== "DỌN";
  for (const id of [
    "cleanup-scope",
    "cleanup-days",
    "preview-cleanup",
    "cleanup-confirmation",
  ])
    document.querySelector("#" + id).disabled = cleanupBusy;
}
function clearCleanupPreview() {
  cleanupPreview = null;
  document.querySelector("#cleanup-preview").hidden = true;
  document.querySelector("#cleanup-confirmation").value = "";
  updateCleanupControls();
}
for (const id of ["cleanup-scope", "cleanup-days"])
  document.querySelector("#" + id).addEventListener("input", () => {
    clearCleanupPreview();
    document.querySelector("#cleanup-status").textContent =
      "Hãy xem trước với lựa chọn mới.";
  });
document.querySelector("#cleanup-confirmation").oninput = updateCleanupControls;
document.querySelector("#preview-cleanup").onclick = async () => {
  const days = document.querySelector("#cleanup-days");
  if (!days.reportValidity()) return;
  clearCleanupPreview();
  cleanupBusy = true;
  updateCleanupControls();
  const status = document.querySelector("#cleanup-status");
  status.textContent = "Đang tìm dữ liệu cũ…";
  try {
    const response = await apiFetch("/api/cleanup/preview", {
      method: "POST",
      body: JSON.stringify({
        scope: document.querySelector("#cleanup-scope").value,
        days: Number(days.value),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error);
    cleanupPreview = data;
    document.querySelector("#cleanup-summary").textContent =
      "Sẽ dọn " +
      data.items +
      (data.scope === "history" ? " nội dung lượt" : " nhiệm vụ") +
      " thuộc " +
      data.tasks +
      " nhiệm vụ kết thúc trước " +
      new Date(data.cutoff).toLocaleString("vi-VN") +
      ". Nội dung chính khoảng " +
      Math.ceil(data.content_bytes / 1024) +
      " KiB; không phải dung lượng đĩa sẽ giảm. Giữ " +
      data.protected +
      " nhiệm vụ có liên kết.";
    const examples = document.querySelector("#cleanup-examples");
    examples.replaceChildren();
    for (const item of data.examples)
      examples.append(el("li", item.id + " · " + item.prompt));
    document.querySelector("#cleanup-preview").hidden = false;
    status.textContent = data.items
      ? "Trên đây là tối đa 5 mục đầu. Bản xem trước có hiệu lực 5 phút. Bản sao được giữ trong thư mục backups cạnh cơ sở dữ liệu."
      : "Không có dữ liệu phù hợp; chưa xóa gì.";
  } catch (e) {
    status.textContent = e.message;
  } finally {
    cleanupBusy = false;
    updateCleanupControls();
  }
};
document.querySelector("#apply-cleanup").onclick = async () => {
  if (
    cleanupBusy ||
    !cleanupPreview?.items ||
    document.querySelector("#cleanup-confirmation").value !== "DỌN"
  )
    return;
  const token = cleanupPreview.token;
  cleanupBusy = true;
  updateCleanupControls();
  const status = document.querySelector("#cleanup-status");
  status.textContent = "Đang lưu bản sao và dọn…";
  try {
    const response = await apiFetch("/api/cleanup/apply", {
      method: "POST",
      body: JSON.stringify({ token, confirmation: "DỌN" }),
    });
    const data = await response.json();
    if (data.backup_file) {
      const link = document.querySelector("#cleanup-backup");
      link.href = "/api/backups/" + encodeURIComponent(data.backup_file);
      link.hidden = false;
    }
    if (!response.ok) throw Error(data.error);
    status.textContent =
      data.message +
      " Đã dọn " +
      data.items +
      " mục. Bản sao vẫn được giữ để bạn tải hoặc khôi phục.";
    lastTaskSignature = null;
    await refresh();
  } catch (e) {
    status.textContent = e.message;
  } finally {
    cleanupBusy = false;
    clearCleanupPreview();
  }
};
checkHealth();
async function viewChecks(id) {
  document.querySelector("#dialog-title").textContent = "Kiểm tra cú pháp";
  try {
    const response = await apiFetch("/api/tasks/" + id + "/checks");
    const data = await response.json();
    if (!response.ok) throw Error(data.error);
    document.querySelector("#file-list").replaceChildren();
    document.querySelector("#download-file").hidden = true;
    const names = {
      passed: "Đạt cú pháp ở các tệp được hỗ trợ",
      failed: "Phát hiện lỗi cú pháp",
      not_supported: "Chưa hỗ trợ kiểm tra các loại tệp này",
      unavailable: "Chưa kiểm tra được",
    };
    document.querySelector("#file-notice").textContent =
      (names[data.status] || data.status) +
      " · Đã kiểm tra: " +
      data.checked +
      " · Bỏ qua: " +
      data.skipped;
    document.querySelector("#file-content").textContent =
      data.message +
      (data.requirements?.issues?.length
        ? "\n\nChưa đáp ứng yêu cầu:\n" + data.requirements.issues.join("\n")
        : "") +
      "\n\n" +
      data.findings
        .map(
          (item) =>
            item.path +
            " · " +
            {
              passed: "Đạt",
              failed: "Lỗi",
              skipped: "Bỏ qua",
              unavailable: "Chưa kiểm tra được",
            }[item.status] +
            "\n" +
            item.message,
        )
        .join("\n\n");
    document.querySelector("#file-dialog").showModal();
  } catch (e) {
    reportError(e.message);
  }
}
const templates = {
  plan: {
    product: false,
    prompt:
      "Lập kế hoạch xây một ứng dụng quản lý công việc cá nhân. Nêu 3 tính năng cơ bản, các bước thực hiện và tiêu chí hoàn thành. Trả lời ngắn gọn bằng tiếng Việt.",
  },
  web: {
    product: true,
    prompt:
      "Tạo ứng dụng ghi chú bằng HTML, CSS và JavaScript thuần: thêm, sửa, xóa và tìm kiếm ghi chú; lưu bằng localStorage. Giao diện tiếng Việt, dùng được trên điện thoại. Không cần thư viện ngoài. Trả đầy đủ index.html, style.css, app.js và README.md hướng dẫn mở trang. Không tuyên bố đã chạy kiểm thử.",
  },
  python: {
    product: true,
    prompt:
      "Tạo ứng dụng quản lý việc cần làm trên dòng lệnh bằng Python 3.12, chỉ dùng thư viện chuẩn. Có thêm, liệt kê, đánh dấu hoàn thành; lưu dữ liệu vào JSON trong thư mục người dùng chọn. Không tự xóa tệp. Trả main.py, tests/test_main.py với unittest và README.md hướng dẫn chạy và kiểm thử bằng tiếng Việt.",
  },
  data: {
    product: true,
    prompt:
      "Tạo bộ tệp dữ liệu JSON mẫu cho ứng dụng ghi chú: notes.json chứa 3 ghi chú gồm id, title, content, created_at; config.json chứa cấu hình không có thông tin bí mật; README.md mô tả từng trường bằng tiếng Việt. Dùng JSON chuẩn, không comment hay dấu phẩy cuối.",
  },
};
let parentTask = null;
const DRAFT_KEY = "bao-mat.draft.v1";
function showRequirements() {
  const files = {
    web: "index.html, style.css, app.js, README.md",
    python: "main.py, tests/test_main.py, README.md",
    data: "notes.json (3 ghi chú), config.json, README.md",
  };
  const chosen = files[document.querySelector("#task-template").value],
    checkbox = document.querySelector("#product");
  checkbox.disabled = Boolean(chosen || parentTask);
  if (checkbox.disabled) checkbox.checked = true;
  document.querySelector("#template-requirements").textContent = parentTask
    ? "Đang sửa sản phẩm cũ và giữ tiêu chí gốc nếu có. Muốn tạo theo mẫu mới, chọn mẫu ở trên để bắt đầu nhiệm vụ độc lập."
    : chosen
      ? "Tệp thực tế bắt buộc: " +
        chosen +
        ". Chỉ hướng dẫn trong README chưa được tính là hoàn thành."
      : "";
  document.querySelector("#output-kind").textContent = checkbox.checked
    ? "Loại nhiệm vụ: tạo bộ tệp · có tải ZIP khi bộ tệp hợp lệ"
    : "Loại nhiệm vụ: văn bản · chỉ có báo cáo .md, không tạo ZIP";
}
function currentDraft() {
  return {
    prompt: document.querySelector("#prompt").value,
    mode: document.querySelector("#mode").value,
    product: document.querySelector("#product").checked,
    parent_id: parentTask,
    template: document.querySelector("#task-template").value,
    expert: document.querySelector("#expert").value,
    document_ids: [...selectedDocuments],
    project_id: selectedProject,
    call_limit: Number(document.querySelector("#call-limit").value),
  };
}
function persistDraft() {
  showRequirements();
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(currentDraft()));
    document.querySelector("#draft-status").textContent =
      "Đã lưu nháp trên trình duyệt này. Không nhập khóa API vào yêu cầu.";
  } catch {
    document.querySelector("#draft-status").textContent =
      "Trình duyệt không cho lưu nháp; hãy giữ lại yêu cầu trước khi đóng trang.";
  }
}
function restoreDraft() {
  try {
    const saved = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
    if (!saved) {
      document.querySelector("#mode").value = "ollama";
      return;
    }
    if (
      typeof saved.prompt !== "string" ||
      saved.prompt.length > 4000 ||
      !["demo", "ollama", "ai"].includes(saved.mode)
    )
      return;
    document.querySelector("#prompt").value = saved.prompt;
    if (
      typeof saved.project_id === "string" &&
      /^[a-zA-Z0-9_-]{1,64}$/.test(saved.project_id)
    )
      selectedProject = saved.project_id;
    if (Array.isArray(saved.document_ids))
      selectedDocuments = saved.document_ids
        .filter((id) => typeof id === "string")
        .slice(0, 5);
    document.querySelector("#mode").value = saved.mode;
    document.querySelector("#product").checked = saved.product === true;
    if (saved.expert === "auto" || Object.hasOwn(expertNames, saved.expert))
      document.querySelector("#expert").value = saved.expert;
    if (
      Number.isInteger(saved.call_limit) &&
      saved.call_limit >= 1 &&
      saved.call_limit <= 100
    ) {
      document.querySelector("#call-limit").value = saved.call_limit;
      budgetTouched = true;
    }
    document.querySelector("#task-template").value = Object.hasOwn(
      templates,
      saved.template,
    )
      ? saved.template
      : "";
    if (
      typeof saved.parent_id === "string" &&
      /^[a-zA-Z0-9_-]{1,64}$/.test(saved.parent_id)
    ) {
      parentTask = saved.parent_id;
      document.querySelector("#revision-note").textContent =
        "Đang chỉnh sửa sản phẩm cũ: " + parentTask;
      document.querySelector("#revision-note").hidden = false;
      document.querySelector("#cancel-revision").hidden = false;
    }
    document.querySelector("#draft-status").textContent =
      "Đã khôi phục bản nháp và chế độ xử lý.";
  } catch {
    document.querySelector("#draft-status").textContent =
      "Chưa đọc được bản nháp trên trình duyệt.";
  }
}
for (const id of ["prompt", "mode", "product", "expert", "call-limit"])
  document
    .querySelector("#" + id)
    .addEventListener(id === "prompt" ? "input" : "change", persistDraft);
document.querySelector("#call-limit").addEventListener("input", () => {
  budgetTouched = true;
  persistDraft();
});
document.querySelector("#clear-draft").onclick = () => {
  if (
    document.querySelector("#prompt").value.trim() &&
    !confirm("Xóa yêu cầu đang soạn? Nhiệm vụ đã giao không bị xóa.")
  )
    return;
  document.querySelector("#prompt").value = "";
  selectedDocuments = [];
  window.dispatchEvent(new Event("workspace:documents"));
  document.querySelector("#product").checked = false;
  document.querySelector("#task-template").value = "";
  clearRevision();
};
document.querySelector("#task-template").onchange = (event) => {
  const template = templates[event.target.value];
  if (!template) return;
  if (
    (document.querySelector("#prompt").value.trim() || parentTask) &&
    !confirm("Thay yêu cầu đang soạn bằng mẫu và bỏ chọn phiên bản gốc?")
  ) {
    event.target.value = "";
    return;
  }
  clearRevision();
  document.querySelector("#prompt").value = template.prompt;
  document.querySelector("#product").checked = template.product;
  document.querySelector("#prompt").focus();
  persistDraft();
};
function clearRevision() {
  parentTask = null;
  document.querySelector("#revision-note").hidden = true;
  document.querySelector("#cancel-revision").hidden = true;
  persistDraft();
}
document.querySelector("#cancel-revision").onclick = clearRevision;
async function beginRevision(task) {
  window.WorkspaceUI?.showView("workspace");
  try {
    const response = await apiFetch("/api/tasks/" + task.id + "/files");
    const data = await response.json();
    if (!response.ok) throw Error(data.error);
    parentTask = task.id;
    selectedProject = task.project_id || task.runtime?.project_id || "default";
    if (document.querySelector("#task-project"))
      document.querySelector("#task-project").value = selectedProject;
    document.querySelector("#task-template").value = "";
    document.querySelector("#product").checked = true;
    document.querySelector("#mode").value = task.mode;
    document.querySelector("#expert").value = Object.hasOwn(
      expertNames,
      task.expert,
    )
      ? task.expert
      : "auto";
    if (task.call_limit) {
      document.querySelector("#call-limit").value = task.call_limit;
      budgetTouched = true;
    }
    const note = document.querySelector("#revision-note");
    note.textContent =
      "Đang sửa bản " +
      task.id +
      ". Bản gốc được giữ nguyên. " +
      (task.requirements?.required_files?.length
        ? "Tệp bắt buộc: " + task.requirements.required_files.join(", ")
        : "Bản gốc chưa có bộ tiêu chí mẫu; chọn mẫu ở trên nếu bạn muốn tạo sản phẩm mới theo mẫu.");
    note.hidden = false;
    document.querySelector("#cancel-revision").hidden = false;
    const prompt = document.querySelector("#prompt");
    prompt.value = "";
    prompt.focus();
    prompt.scrollIntoView({ behavior: "smooth", block: "center" });
    persistDraft();
  } catch (e) {
    reportError(e.message);
  }
}
async function viewDiff(id) {
  document.querySelector("#dialog-title").textContent = "So sánh phiên bản";
  try {
    const response = await apiFetch("/api/tasks/" + id + "/diff");
    const data = await response.json();
    if (!response.ok) throw Error(data.error);
    const list = document.querySelector("#file-list"),
      content = document.querySelector("#file-content");
    list.replaceChildren();
    document.querySelector("#download-file").hidden = true;
    document.querySelector("#file-notice").textContent =
      "So với bản gốc " +
      data.parent_id +
      ". Các thay đổi do mô hình tạo, chưa được thực thi.";
    const names = { added: "Thêm", deleted: "Xóa", modified: "Sửa" };
    for (const change of data.changes) {
      const button = el("button", names[change.kind] + " · " + change.path);
      button.onclick = () => {
        content.textContent = change.diff || "(Tệp rỗng)";
      };
      list.append(button);
    }
    content.textContent = data.changes.length
      ? data.changes[0].diff
      : "Không có thay đổi nội dung tệp.";
    document.querySelector("#file-dialog").showModal();
  } catch (e) {
    reportError(e.message);
  }
}
const opened = new Set();
const memoryField = document.querySelector("#memory"),
  memoryStatus = document.querySelector("#memory-status");
document.querySelector("#save-memory").disabled = true;
memoryField.disabled = true;
async function loadMemory() {
  try {
    const response = await apiFetch("/api/memory");
    if (!response.ok) throw Error("Không tải được bộ nhớ; hãy tải lại trang");
    const data = await response.json();
    memoryField.value = data.content;
    memoryField.disabled = false;
    document.querySelector("#save-memory").disabled = false;
  } catch (e) {
    memoryStatus.textContent = e.message;
  }
}
document.querySelector("#memory-form").onsubmit = async (event) => {
  event.preventDefault();
  const button = document.querySelector("#save-memory");
  button.disabled = true;
  try {
    const response = await apiFetch("/api/memory", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: memoryField.value }),
    });
    if (!response.ok) throw Error("Chưa lưu được bộ nhớ");
    memoryStatus.textContent = "Đã lưu. Nhiệm vụ mới sẽ dùng bộ nhớ này.";
  } catch (e) {
    memoryStatus.textContent = e.message;
  } finally {
    button.disabled = false;
  }
};
loadMemory();
async function taskAction(id, action, button) {
  const message =
    action === "cancel"
      ? "Hủy nhiệm vụ? Ứng dụng sẽ đóng luồng Ollama và chuyển sang việc tiếp theo. Việc dừng tính bên trong máy chủ phụ thuộc Ollama. OpenAI hiện vẫn chờ yêu cầu kết thúc."
      : "Bạn đã xem và chấp nhận kết quả này? Việc duyệt không chạy hay triển khai mã.";
  if (!confirm(message)) return;
  button.disabled = true;
  try {
    const response = await apiFetch("/api/tasks/" + id + "/" + action, {
      method: "POST",
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error);
    await refresh();
  } catch (e) {
    reportError(e.message);
  } finally {
    button.disabled = false;
  }
}
async function retry(task, button) {
  const id = task.id;
  if (
    !confirm(
      "Tạo một lượt chạy mới từ bước đầu và giữ nguyên kết quả cũ? OpenAI có thể phát sinh thêm phí; Ollama chạy trên máy.",
    )
  )
    return;
  const chosen = prompt(
    "Giới hạn lượt gọi cho lượt chạy mới (1–100), gồm chuyên gia và đội thực thi:",
    String(task.call_limit || 20),
  );
  if (chosen === null) return;
  const limit = Number(chosen);
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    reportError("Giới hạn lượt gọi phải từ 1 đến 100");
    return;
  }
  button.disabled = true;
  try {
    const response = await apiFetch("/api/tasks/" + id + "/retry", {
      method: "POST",
      body: JSON.stringify({ call_limit: limit }),
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error);
    await jumpTask(data.id);
  } catch (e) {
    reportError(e.message);
  } finally {
    button.disabled = false;
  }
}
async function jumpTask(id) {
  pageOffset = 0;
  document.querySelector("#search").value = id;
  document.querySelector("#filter").value = "all";
  window.WorkspaceUI?.showView("tasks");
  await refresh();
}
let submitting = false,
  queueFull = false,
  lastTaskSignature = null;
let pageLimit = 20;
const renderedTaskStates = new WeakMap();
let pendingTaskDelete = null,
  taskDeleteBusy = false,
  deletePreviewSequence = 0;
function notifyWorkspace(message, backupFile) {
  const notice = document.querySelector("#workspace-notice");
  notice.textContent = message;
  notice.hidden = !message;
  if (backupFile) {
    const link = document.querySelector("#task-delete-backup");
    link.href = "/api/backups/" + encodeURIComponent(backupFile);
    link.hidden = false;
  }
}
function reportError(message) {
  document.querySelector("#error").textContent = message;
  if (!message || document.querySelector("#view-workspace").hidden)
    notifyWorkspace(message);
}
async function deleteTask(task) {
  if (taskDeleteBusy) return;
  const sequence = ++deletePreviewSequence;
  pendingTaskDelete = null;
  const dialog = document.querySelector("#task-delete-dialog");
  document.querySelector("#task-delete-name").textContent = task.prompt;
  document.querySelector("#task-delete-summary").textContent =
    "Đang xem nội dung của công việc…";
  document.querySelector("#task-delete-status").textContent = "";
  document.querySelector("#confirm-task-delete").disabled = true;
  if (!dialog.open) dialog.showModal();
  try {
    const response = await apiFetch(
      "/api/tasks/" + task.id + "/delete-preview",
      { method: "POST", body: "{}" },
    );
    const preview = await response.json();
    if (!response.ok) throw Error(preview.error);
    if (sequence !== deletePreviewSequence || !dialog.open) return;
    document.querySelector("#task-delete-summary").textContent =
      "Sẽ xóa kết quả, bộ tệp, báo cáo và " +
      preview.steps +
      " lượt lịch sử của riêng công việc này. " +
      (preview.related
        ? "Có " +
          preview.related +
          " công việc liên quan: các bản đó và bản chụp nguồn của chúng được giữ. Chỉ giữ mã và tên ngắn của việc đã xóa để nhận biết liên kết. "
        : "") +
      (window.WorkspaceUI?.deletionWarning(task.id) || "");
    pendingTaskDelete = { id: task.id, token: preview.token };
    document.querySelector("#confirm-task-delete").disabled = false;
  } catch (error) {
    if (sequence === deletePreviewSequence)
      document.querySelector("#task-delete-status").textContent = error.message;
  }
}
function cancelTaskDelete() {
  if (taskDeleteBusy) return;
  deletePreviewSequence++;
  pendingTaskDelete = null;
  document.querySelector("#task-delete-dialog").close();
}
document.querySelector("#cancel-task-delete").onclick = cancelTaskDelete;
document
  .querySelector("#task-delete-dialog")
  .addEventListener("cancel", (event) => {
    event.preventDefault();
    cancelTaskDelete();
  });
document.querySelector("#confirm-task-delete").onclick = async () => {
  if (!pendingTaskDelete || taskDeleteBusy) return;
  taskDeleteBusy = true;
  const chosen = { ...pendingTaskDelete };
  document.querySelector("#confirm-task-delete").disabled = true;
  document.querySelector("#cancel-task-delete").disabled = true;
  document.querySelector("#task-delete-status").textContent =
    "Đang lưu bản sao và xóa công việc…";
  try {
    const response = await apiFetch("/api/tasks/" + chosen.id + "/delete", {
      method: "POST",
      body: JSON.stringify({ token: chosen.token, confirmation: chosen.id }),
    });
    const data = await response.json();
    if (data.backup_file)
      notifyWorkspace(
        response.ok ? data.message : data.error,
        data.backup_file,
      );
    if (!response.ok) throw Error(data.error);
    window.WorkspaceUI?.taskDeleted(chosen.id);
    opened.delete(chosen.id);
    lastTaskSignature = null;
    document.querySelector("#file-list").replaceChildren();
    document.querySelector("#file-content").textContent = "";
    pendingTaskDelete = null;
    document.querySelector("#task-delete-dialog").close();
    notifyWorkspace(data.message, data.backup_file);
    await refresh();
  } catch (error) {
    document.querySelector("#task-delete-status").textContent =
      error.message + " Đóng cửa sổ và bấm Xóa để xem trước lại.";
    pendingTaskDelete = null;
  } finally {
    taskDeleteBusy = false;
    document.querySelector("#cancel-task-delete").disabled = false;
  }
};
function renderTaskCard(t) {
  const card = el("article", "");
  card.className = "task-card task-row";
  card.dataset.taskId = t.id;
  card.dataset.status = t.status;
  const heading = el("div", "");
  heading.className = "task-row-heading";
  const icon = el("button", t.product ? "▧" : "▤");
  icon.className = "task-icon secondary";
  icon.setAttribute("aria-label", "Mở công việc: " + t.prompt);
  icon.title = "Mở công việc";
  icon.onclick = () => window.WorkspaceUI?.openTask(t.id);
  const title = el("button", t.prompt);
  title.className = "task-title-button";
  title.onclick = () => window.WorkspaceUI?.openTask(t.id);
  const state = el("span", labels[t.status] || t.status);
  state.className = "task-state";
  heading.append(icon, title, state);
  card.append(heading, el("p", t.stage));
  const methods = {
    per_file: "Sinh từng tệp riêng",
    bundle: "Sinh cả bộ tệp",
    text: "Sinh văn bản",
    demo: "Mô phỏng",
    manual: "Bạn chỉnh sửa thủ công",
  };
  const timing = el("p", "");
  timing.className = "progress-text";
  timing.dataset.duration = "";
  timing.dataset.start = t.started_at || "";
  timing.dataset.finish = t.finished_at || "";
  timing.dataset.steps = String(t.completed_steps || 0);
  card.append(timing);
  const actions = el("div", "");
  actions.className = "task-row-actions";
  const inspect = el("button", "Mở kết quả");
  inspect.onclick = () => window.WorkspaceUI?.openTask(t.id);
  actions.append(inspect);
  if (t.has_output) {
    const report = el("a", "Tải báo cáo ↓");
    report.href = "/api/tasks/" + t.id + "/export/all";
    actions.append(report);
  }
  const productReady =
    t.product && ["completed", "needs_review", "approved"].includes(t.status);
  if (productReady) {
    const files = el("button", "Xem bộ tệp");
    files.className = "secondary";
    files.onclick = () => viewFiles(t.id);
    const zip = el("a", "Tải mã nguồn ZIP");
    zip.href = "/api/tasks/" + t.id + "/artifact.zip";
    actions.append(files, zip);
  }
  if (!["queued", "running"].includes(t.status)) {
    const remove = el("button", "Xóa công việc");
    remove.className = "danger secondary";
    remove.onclick = () => deleteTask(t);
    actions.append(remove);
  }
  card.append(actions);
  const more = el("details", "");
  more.open = opened.has(t.id);
  more.append(el("summary", "Thao tác và thông tin"));
  more.addEventListener("toggle", () => {
    if (more.isConnected) {
      if (more.open) opened.add(t.id);
      else opened.delete(t.id);
    }
  });
  more.append(el("small", "Mã công việc: " + t.id));
  more.append(
    el(
      "p",
      (methods[t.generation_method] || t.generation_method) +
        " · " +
        t.model_calls +
        " lượt yêu cầu mô hình",
    ),
  );
  if (t.call_limit)
    more.append(
      el(
        "p",
        (t.expert_name
          ? "ECC · " + t.expert_name
          : expertNames[t.expert] || "Đội cơ bản") +
          " → Đội thực thi · lượt gọi " +
          t.model_calls +
          "/" +
          t.call_limit,
      ),
    );
  if (t.documents?.length)
    more.append(
      el("p", "Đính kèm: " + t.documents.map((item) => item.title).join(", ")),
    );
  if (t.requirements?.required_files?.length)
    more.append(
      el("p", "Tệp bắt buộc: " + t.requirements.required_files.join(", ")),
    );
  more.append(
    el(
      "p",
      new Date(t.created).toLocaleString("vi-VN") +
        " · " +
        (t.mode === "demo" ? "MÔ PHỎNG" : t.mode.toUpperCase()),
    ),
  );
  const action = (name, callback) => {
    const button = el("button", name);
    button.className = "secondary";
    button.onclick = () => callback(button);
    more.append(button);
  };
  action("Lịch sử từng bước", () => viewHistory(t.id));
  if (t.retry_of) {
    if (t.retry_of_deleted)
      more.append(
        el("p", "Lượt trước đã xóa; bản chụp trong công việc này vẫn giữ."),
      );
    else action("Xem lượt trước", () => jumpTask(t.retry_of));
  }
  if (t.retry_id && !t.retry_deleted)
    action("Xem lượt chạy lại", () => jumpTask(t.retry_id));
  if (productReady) {
    action("Kiểm tra cú pháp", () => viewChecks(t.id));
    action("Yêu cầu chỉnh sửa", () => beginRevision(t));
    if (t.parent_id) {
      if (t.parent_deleted)
        more.append(
          el("p", "Bản gốc đã xóa · vẫn so sánh được bằng bản chụp nguồn."),
        );
      action("So sánh với bản gốc", () => viewDiff(t.id));
    }
  }
  if (["queued", "running"].includes(t.status))
    action("Hủy nhiệm vụ", (button) => taskAction(t.id, "cancel", button));
  if (
    t.mode !== "demo" &&
    ["completed", "needs_review"].includes(t.status) &&
    (t.has_result || (t.generation_method === "legacy" && t.has_output))
  )
    action("Duyệt kết quả", (button) => taskAction(t.id, "approve", button));
  if (
    (!t.retry_id || t.retry_deleted) &&
    ["failed", "interrupted", "cancelled", "needs_review"].includes(t.status)
  )
    action("Chạy lại từ đầu", (button) => retry(t, button));
  card.append(more);
  return card;
}
async function refresh() {
  const version = ++refreshVersion;
  try {
    const listingVisible =
      document.querySelector("#view-tasks").hidden === false;
    const params = new URLSearchParams({
      q: document.querySelector("#search").value,
      status: document.querySelector("#filter").value,
      offset: String(pageOffset),
      compact: "1",
    });
    if (document.querySelector("#project-filter")?.value)
      params.set("project_id", document.querySelector("#project-filter").value);
    const [teamResponse, response] = await Promise.all([
      apiFetch("/api/team"),
      listingVisible ? apiFetch("/api/tasks?" + params) : Promise.resolve(null),
    ]);
    if (!teamResponse.ok || (response && !response.ok))
      throw Error("Không đọc được trạng thái đội bot");
    const team = await teamResponse.json(),
      data = response ? await response.json() : null;
    if (version !== refreshVersion) return;
    document.querySelector('option[value="ai"]').disabled = !team.ai_available;
    if (!team.ai_available && document.querySelector("#mode").value === "ai") {
      document.querySelector("#mode").value = "demo";
      persistDraft();
      document.querySelector("#draft-status").textContent =
        "OpenAI chưa cấu hình; chuyển sang mô phỏng. Bạn có thể chọn Ollama.";
    }
    document.querySelector("#summary").textContent =
      (Object.entries(team.totals)
        .map(([key, count]) => (labels[key] || key) + ": " + count)
        .join(" · ") || "Chưa có công việc") +
      " · Hàng đợi: " +
      team.queue.waiting +
      "/" +
      team.queue.capacity;
    queuePaused = team.queue.paused;
    document.querySelector("#supervisor-state").textContent =
      team.supervisors_active
        ? "Chuyên gia ECC đang giao việc cho đội thực thi"
        : "Chuyên gia ECC sẵn sàng · chọn theo mẫu hoặc chọn riêng khi giao việc";
    document.querySelector("#queue-state").textContent =
      (queuePaused ? "Đang tạm dừng" : "Sẵn sàng nhận việc") +
      " · " +
      team.queue.waiting +
      "/" +
      team.queue.capacity +
      " việc chờ";
    document.querySelector("#toggle-queue").textContent = queuePaused
      ? "Tiếp tục hàng đợi"
      : "Tạm dừng hàng đợi";
    document.querySelector("#toggle-queue").disabled = queueUpdating;
    queueFull = team.queue.waiting >= team.queue.capacity;
    document.querySelector("#submit").disabled = submitting || queueFull;
    window.dispatchEvent(
      new CustomEvent("workspace:update", {
        detail: { tasks: data?.tasks || [], team },
      }),
    );
    if (!data) return;
    pageLimit = data.limit;
    if (pageOffset > 0 && pageOffset >= data.total) {
      pageOffset = Math.max(
        0,
        Math.floor((data.total - 1) / pageLimit) * pageLimit,
      );
      return refresh();
    }
    document.querySelector("#previous-page").disabled = pageOffset === 0;
    document.querySelector("#next-page").disabled =
      pageOffset + data.limit >= data.total;
    document.querySelector("#page-info").textContent = data.tasks.length
      ? "Kết quả " +
        (pageOffset + 1) +
        "–" +
        Math.min(pageOffset + data.tasks.length, data.total) +
        " / " +
        data.total
      : "0 kết quả";
    const signature = JSON.stringify(data.tasks);
    if (signature === lastTaskSignature) {
      updateDurations();
      return;
    }
    lastTaskSignature = signature;
    const root = document.querySelector("#tasks");
    if (!data.tasks.length) {
      root.replaceChildren(
        el("p", "Không có công việc phù hợp. Thử đổi từ khóa hoặc bộ lọc."),
      );
    } else {
      root.querySelectorAll(":scope > p").forEach((node) => node.remove());
      const existing = new Map(
        [...root.children].map((node) => [node.dataset.taskId, node]),
      );
      const wanted = new Set(data.tasks.map((task) => task.id));
      for (const [id, node] of existing) if (!wanted.has(id)) node.remove();
      data.tasks.forEach((task, index) => {
        const state = JSON.stringify(task);
        let node = existing.get(task.id);
        if (!node || renderedTaskStates.get(node) !== state) {
          node?.remove();
          node = renderTaskCard(task);
          renderedTaskStates.set(node, state);
        }
        if (root.children[index] !== node)
          root.insertBefore(node, root.children[index] || null);
      });
    }
    updateDurations();
  } catch (error) {
    if (version === refreshVersion) notifyWorkspace(error.message);
  }
}
window.addEventListener("workspace:view", () => {
  refreshVersion++;
  lastTaskSignature = null;
  if (document.querySelector("#view-tasks").hidden)
    document.querySelector("#tasks").replaceChildren();
  refresh();
});
let searchTimer;
document.querySelector("#search").oninput = () => {
  clearTimeout(searchTimer);
  pageOffset = 0;
  refreshVersion++;
  searchTimer = setTimeout(refresh, 300);
};
document.querySelector("#filter").onchange = () => {
  pageOffset = 0;
  refresh();
};
document.querySelector("#previous-page").onclick = () => {
  pageOffset = Math.max(0, pageOffset - pageLimit);
  refresh();
};
document.querySelector("#next-page").onclick = () => {
  pageOffset += pageLimit;
  refresh();
};
document.querySelector("#form").onsubmit = async (event) => {
  event.preventDefault();
  const button = document.querySelector("#submit"),
    request = currentDraft();
  submitting = true;
  button.disabled = true;
  try {
    const response = await apiFetch("/api/tasks", {
      method: "POST",
      body: JSON.stringify(request),
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error);
    reportError("");
    if (JSON.stringify(currentDraft()) === JSON.stringify(request)) {
      document.querySelector("#prompt").value = "";
      document.querySelector("#task-template").value = "";
      selectedDocuments = [];
      window.dispatchEvent(new Event("workspace:documents"));
      clearRevision();
      persistDraft();
    }
    pageOffset = 0;
    document.querySelector("#search").value = "";
    document.querySelector("#filter").value = "all";
    await refresh();
    if (!document.querySelector("#view-workspace").hidden)
      await window.WorkspaceUI?.openTask(data.id);
  } catch (error) {
    reportError(error.message);
  } finally {
    submitting = false;
    button.disabled = queueFull;
  }
};
restoreDraft();
showRequirements();
refresh();
setInterval(refresh, 2000);
