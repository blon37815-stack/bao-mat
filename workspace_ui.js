// Navigation, bot setup, document library and a persistent product workbench.
(() => {
  const $ = (selector) => document.querySelector(selector);
  const pages = {
    workspace: [
      "Trao đổi với đội bot",
      "Giao việc và đọc kết quả đang chọn. Lịch sử nằm riêng trong mục Công việc.",
    ],
    tasks: [
      "Công việc của bạn",
      "Mở công việc khi cần xem; tải kết quả hoặc xóa việc đã kết thúc.",
    ],
    team: [
      "Đội bot của bạn",
      "Biết từng bot làm gì, đang làm việc nào và thiết lập riêng.",
    ],
    documents: [
      "Tài liệu & bộ nhớ",
      "Lưu điều đội cần biết. Bạn chọn nội dung gửi theo từng nhiệm vụ.",
    ],
    resources: [
      "Phân công & tài nguyên",
      "Theo dõi máy và kiểm soát số việc chờ, lượt gọi mô hình.",
    ],
    settings: [
      "Thiết lập ứng dụng",
      "Kết nối Ollama, tải bản sao lưu và dọn dữ liệu cũ.",
    ],
  };
  let currentView = null,
    selectedRefreshing = false;
  const deletedTaskIds = new Set();
  let selectedTask = null,
    files = [],
    originals = [],
    fileIndex = 0;
  let editorDirty = false,
    savingProduct = false,
    loadSequence = 0,
    previewSequence = 0;
  let documents = [],
    documentId = null,
    documentDirty = false,
    documentSaving = false,
    documentSequence = 0,
    documentEditVersion = 0;
  let bots = [],
    editedBot = null,
    botSignature = "",
    botsLoading = false;

  function showView(name) {
    if (!Object.hasOwn(pages, name)) name = "workspace";
    if (currentView === name) return;
    currentView = name;
    if (name !== "workspace") {
      loadSequence++;
      previewSequence++;
      $("#product-preview").srcdoc = "";
    }
    for (const [id] of Object.entries(pages))
      $("#view-" + id).hidden = id !== name;
    document.querySelectorAll("[data-view]").forEach((button) => {
      if (button.dataset.view === name)
        button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    $("#page-title").textContent = pages[name][0];
    $("#page-description").textContent = pages[name][1];
    history.replaceState(null, "", "#" + name);
    window.dispatchEvent(
      new CustomEvent("workspace:view", { detail: { name } }),
    );
    if (name === "workspace") refreshSelectedTask();
    if (
      name === "workspace" &&
      selectedTask &&
      $("#tab-preview").getAttribute("aria-selected") === "true"
    )
      refreshPreview();
    if (name === "team") loadBots(true);
  }
  function showTasks(status = "all") {
    pageOffset = 0;
    $("#search").value = "";
    $("#filter").value = status;
    showView("tasks");
    refresh();
  }
  $("#open-tasks").onclick = () => showTasks();
  document
    .querySelectorAll("[data-task-filter]")
    .forEach(
      (button) => (button.onclick = () => showTasks(button.dataset.taskFilter)),
    );
  document
    .querySelectorAll("[data-view]")
    .forEach(
      (button) => (button.onclick = () => showView(button.dataset.view)),
    );
  $(".brand").onclick = (event) => {
    event.preventDefault();
    showView("workspace");
  };
  $("#new-task").onclick = () => {
    showView("workspace");
    $(".workspace-grid").classList.remove("expanded");
    $("#expand-inspector").setAttribute("aria-label", "Mở rộng khung sản phẩm");
    $("#expand-inspector").title = "Mở rộng khung sản phẩm";
    $("#compose-panel").scrollIntoView({ behavior: "smooth", block: "start" });
    $("#prompt").focus();
  };
  $("#expand-inspector").onclick = () => {
    const expanded = $(".workspace-grid").classList.toggle("expanded");
    $("#expand-inspector").setAttribute(
      "aria-label",
      expanded ? "Thu nhỏ khung sản phẩm" : "Mở rộng khung sản phẩm",
    );
    $("#expand-inspector").title = expanded
      ? "Thu nhỏ khung sản phẩm"
      : "Mở rộng khung sản phẩm";
  };
  window.addEventListener("workspace:health", ({ detail }) => {
    $("#sidebar-health").textContent =
      detail.status === "ready"
        ? "Ollama sẵn sàng · " + detail.model
        : detail.status === "model_missing"
          ? "Ollama đang mở · cần tải mô hình"
          : "Chưa kết nối Ollama · có thể dùng mô phỏng";
  });
  window.addEventListener("workspace:update", ({ detail }) => {
    const { team } = detail;
    const total = Object.values(team.totals).reduce(
      (sum, count) => sum + count,
      0,
    );
    $("#stat-total").textContent = total;
    $("#nav-task-count").textContent = total;
    $("#workspace-task-count").textContent = total;
    $("#stat-running").textContent = team.totals.running || 0;
    $("#stat-waiting").textContent = team.queue.waiting;
    $("#stat-review").textContent = team.totals.needs_review || 0;
    if (selectedTask)
      document
        .querySelectorAll(".task-card")
        .forEach((card) =>
          card.classList.toggle(
            "selected",
            card.dataset.taskId === selectedTask.id,
          ),
        );
    refreshSelectedTask();
  });
  async function refreshSelectedTask() {
    if (
      selectedRefreshing ||
      currentView !== "workspace" ||
      !selectedTask ||
      editorDirty ||
      savingProduct ||
      !["queued", "running"].includes(selectedTask.status)
    )
      return;
    const id = selectedTask.id,
      sequence = loadSequence;
    selectedRefreshing = true;
    try {
      const response = await apiFetch("/api/tasks/" + id);
      const latest = await response.json();
      if (
        sequence !== loadSequence ||
        currentView !== "workspace" ||
        selectedTask?.id !== id ||
        editorDirty ||
        savingProduct
      )
        return;
      if (response.status === 404) {
        clearInspector(true);
        notifyWorkspace("Công việc đã được xóa ở phiên khác.");
        return;
      }
      if (!response.ok) throw Error(latest.error);
      if (
        latest.output !== selectedTask.output ||
        latest.status !== selectedTask.status ||
        latest.stage !== selectedTask.stage
      ) {
        const tab = document
          .querySelector('.inspector-tabs [aria-selected="true"]')
          .id.replace("tab-", "");
        await openTask(latest, tab, true);
      }
    } catch (error) {
      $("#inspector-error").textContent = error.message;
    } finally {
      selectedRefreshing = false;
    }
  }
  function clearInspector(force = false) {
    if (
      savingProduct ||
      (!force &&
        editorDirty &&
        !confirm("Bỏ thay đổi tệp chưa lưu và đóng kết quả?"))
    )
      return;
    loadSequence++;
    previewSequence++;
    selectedTask = null;
    files = [];
    originals = [];
    fileIndex = 0;
    editorDirty = false;
    $("#product-preview").srcdoc = "";
    $("#preview-text").textContent = "";
    $("#product-editor").value = "";
    $("#product-files").replaceChildren();
    $("#inspector-output").replaceChildren();
    $("#inspector-body").hidden = true;
    $("#close-inspector").hidden = true;
    $("#expand-inspector").hidden = true;
    $("#inspector-empty").hidden = false;
    $("#inspector-title").textContent = "Xem kết quả tại đây";
    $("#delete-open-task").hidden = true;
    $(".workspace-grid").classList.remove("expanded");
    $("#expand-inspector").setAttribute("aria-label", "Mở rộng khung sản phẩm");
    $("#expand-inspector").title = "Mở rộng khung sản phẩm";
  }
  $("#close-inspector").onclick = () => clearInspector();
  $("#delete-open-task").onclick = () => {
    if (selectedTask) deleteTask(selectedTask);
  };
  function textBlock(text) {
    const block = el("div", "");
    block.className = "readable-text";
    // Render a small text-only Markdown subset; source HTML is never inserted.
    let code = null;
    for (const line of text.split("\n")) {
      if (line.startsWith("```")) {
        if (code) code = null;
        else {
          code = el("pre", "");
          block.append(code);
        }
      } else if (code) code.textContent += line + "\n";
      else if (/^#{1,4}\s/.test(line))
        block.append(el("h3", line.replace(/^#{1,4}\s/, "")));
      else if (line.trim()) block.append(el("p", line));
    }
    return block;
  }
  function renderOutput() {
    const root = $("#inspector-output");
    root.replaceChildren();
    const output = JSON.parse(selectedTask.output);
    const names = {
      supervise: "Chỉ đạo chuyên gia",
      plan: "Kế hoạch",
      result: "Sản phẩm",
      review: "Kiểm tra",
    };
    for (const [key, value] of Object.entries(output)) {
      root.append(el("h3", names[key] || key));
      let bundle;
      try {
        bundle = key === "result" && JSON.parse(value);
      } catch {}
      if (Array.isArray(bundle?.files)) {
        root.append(
          el(
            "p",
            "Đã lưu " +
              bundle.files.length +
              " tệp. Mở Tệp & chỉnh sửa để đọc từng tệp.",
          ),
        );
        const list = el("ul", "");
        bundle.files.forEach((file) => list.append(el("li", file.path)));
        root.append(list);
      } else
        root.append(textBlock(key === "review" ? reviewText(value) : value));
    }
    if (!Object.keys(output).length)
      root.append(
        el(
          "p",
          "Đội đang xử lý. Kết quả sẽ xuất hiện tại đây khi từng bước hoàn thành.",
        ),
      );
    if (selectedTask.documents?.length)
      root.append(
        el(
          "p",
          "Tài liệu đã gửi: " +
            selectedTask.documents.map((item) => item.title).join(", "),
        ),
      );
  }
  function selectTab(name) {
    for (const id of ["output", "code", "preview"]) {
      $("#tab-" + id).setAttribute("aria-selected", String(name === id));
      $("#inspector-" + id).hidden = name !== id;
    }
    if (name === "preview") refreshPreview();
  }
  for (const id of ["output", "code", "preview"]) {
    $("#tab-" + id).onclick = () => selectTab(id);
    $("#tab-" + id).setAttribute("aria-controls", "inspector-" + id);
    $("#inspector-" + id).setAttribute("role", "tabpanel");
    $("#inspector-" + id).setAttribute("aria-labelledby", "tab-" + id);
  }
  $(".inspector-tabs").onkeydown = (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const tabs = [
      ...document.querySelectorAll(".inspector-tabs button:not(:disabled)"),
    ];
    const current = tabs.indexOf(document.activeElement);
    const index =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) %
            tabs.length;
    event.preventDefault();
    tabs[index].focus();
    tabs[index].click();
  };

  function renderFileTree() {
    const tree = $("#product-files");
    tree.replaceChildren();
    files.forEach((file, index) => {
      const button = el("button", file.path);
      button.setAttribute("aria-current", String(index === fileIndex));
      button.onclick = () => {
        if (!savingProduct) {
          fileIndex = index;
          renderFileTree();
        }
      };
      tree.append(button);
    });
    const file = files[fileIndex];
    $("#editor-path").textContent = file?.path || "Chưa có tệp";
    $("#product-editor").value = file?.content || "";
    $("#delete-product-file").disabled = files.length <= 1 || savingProduct;
    const originalIndex = originals.findIndex(
      (item) => item.path === file?.path,
    );
    $("#product-download-file").href =
      "/api/tasks/" + selectedTask.id + "/file/" + originalIndex;
    $("#product-download-file").hidden = originalIndex < 0;
    const entries = files.filter((item) => /\.html?$/i.test(item.path));
    const previous = $("#preview-entry").value;
    $("#preview-entry").replaceChildren(
      ...entries.map((item) => {
        const option = el("option", item.path);
        option.value = item.path;
        return option;
      }),
    );
    if (entries.some((item) => item.path === previous))
      $("#preview-entry").value = previous;
    $("#preview-entry").disabled = !entries.length;
  }
  function markEditorDirty() {
    editorDirty = true;
    previewSequence++;
    $("#editor-state").textContent =
      "Có thay đổi chưa lưu · bản gốc vẫn được giữ.";
    $("#save-product").disabled = false;
  }
  $("#product-editor").oninput = () => {
    if (!files[fileIndex] || savingProduct) return;
    files[fileIndex].content = $("#product-editor").value;
    markEditorDirty();
  };
  $("#delete-product-file").onclick = () => {
    if (
      savingProduct ||
      files.length <= 1 ||
      !confirm(
        "Bỏ " +
          files[fileIndex].path +
          " khỏi bản sửa? Bản gốc vẫn giữ tệp này. Nhấn Lưu thành phiên bản mới để lưu thay đổi.",
      )
    )
      return;
    files.splice(fileIndex, 1);
    fileIndex = Math.min(fileIndex, files.length - 1);
    markEditorDirty();
    renderFileTree();
  };
  async function openTask(task, tab = "output", passive = false) {
    if (savingProduct) return;
    if (
      !passive &&
      editorDirty &&
      !confirm("Bỏ thay đổi chưa lưu trong khung sản phẩm để mở kết quả này?")
    )
      return;
    const sequence = ++loadSequence;
    previewSequence++;
    try {
      if (typeof task === "string" || typeof task.output !== "string") {
        const response = await apiFetch(
          "/api/tasks/" + (typeof task === "string" ? task : task.id),
        );
        task = await response.json();
        if (!response.ok) throw Error(task.error);
      }
      let product = null;
      if (
        task.product &&
        ["completed", "needs_review", "approved"].includes(task.status)
      ) {
        const response = await apiFetch("/api/tasks/" + task.id + "/files");
        const data = await response.json();
        if (response.ok) product = data;
        else if (tab === "code") throw Error(data.error);
      }
      if (
        sequence !== loadSequence ||
        deletedTaskIds.has(task.id) ||
        (passive && currentView !== "workspace")
      )
        return;
      selectedTask = task;
      originals = product?.files || [];
      files = originals.map((file) => ({ ...file }));
      fileIndex = 0;
      editorDirty = false;
      if (!passive) showView("workspace");
      $("#inspector-empty").hidden = true;
      $("#inspector-body").hidden = false;
      $("#close-inspector").hidden = false;
      $("#expand-inspector").hidden = false;
      $("#inspector-title").textContent = task.prompt;
      $("#inspector-status").textContent =
        (labels[task.status] || task.status) +
        " · " +
        task.stage +
        (task.mode === "demo" ? " · MÔ PHỎNG" : "");
      window.dispatchEvent(new CustomEvent("workspace:task", { detail: task }));
      $("#inspector-error").textContent = "";
      $("#save-product").disabled = true;
      $("#editor-state").textContent = "Bản gốc được giữ nguyên.";
      $("#tab-code").disabled = !files.length;
      $("#tab-preview").disabled = !files.length;
      $("#product-download-zip").hidden = !files.length;
      $("#product-download-zip").href =
        "/api/tasks/" + task.id + "/artifact.zip";
      $("#product-report").href = "/api/tasks/" + task.id + "/export/all";
      $("#product-report").hidden = !Object.keys(JSON.parse(task.output))
        .length;
      $("#ask-revision").hidden = !files.length;
      $("#delete-open-task").hidden = ["queued", "running"].includes(
        task.status,
      );
      renderOutput();
      renderFileTree();
      selectTab(files.length ? tab : "output");
      document
        .querySelectorAll(".task-card")
        .forEach((card) =>
          card.classList.toggle("selected", card.dataset.taskId === task.id),
        );
      if (!passive)
        $("#inspector").scrollIntoView({
          behavior: "smooth",
          block: "nearest",
        });
    } catch (error) {
      reportError(error.message);
    }
  }
  $("#ask-revision").onclick = async () => {
    if (
      editorDirty &&
      !confirm(
        "Nhờ bot sửa từ phiên bản đã lưu? Các thay đổi chưa lưu trong trình soạn thảo chưa được gửi.",
      )
    )
      return;
    await beginRevision(selectedTask);
  };
  $("#save-product").onclick = async () => {
    if (savingProduct || !editorDirty) return;
    savingProduct = true;
    $("#save-product").disabled = true;
    $("#product-editor").readOnly = true;
    $("#delete-product-file").disabled = true;
    let nextId;
    try {
      const response = await apiFetch(
        "/api/tasks/" + selectedTask.id + "/edit",
        { method: "POST", body: JSON.stringify({ files }) },
      );
      const data = await response.json();
      if (!response.ok) throw Error(data.error);
      editorDirty = false;
      nextId = data.id;
    } catch (error) {
      $("#inspector-error").textContent = error.message;
    } finally {
      savingProduct = false;
      $("#product-editor").readOnly = false;
      $("#save-product").disabled = !editorDirty;
      $("#delete-product-file").disabled = files.length <= 1;
    }
    if (nextId) {
      await jumpTask(nextId);
      await openTask(nextId, "code");
      $("#editor-state").textContent =
        "Đã lưu phiên bản mới. Bản gốc được giữ; chưa gọi AI hoặc chạy mã.";
    }
  };
  async function refreshPreview() {
    if (!files.length) return;
    const sequence = ++previewSequence,
      entry = $("#preview-entry").value;
    $("#inspector-error").textContent = "";
    if (!entry) {
      $(".preview-surface").hidden = true;
      $("#preview-text").hidden = false;
      $("#inspector-preview .hint").textContent =
        "Xem nội dung tệp đang chọn · chưa chạy chương trình.";
      let text = files[fileIndex].content;
      if (/\.json$/i.test(files[fileIndex].path)) {
        try {
          text = JSON.stringify(JSON.parse(text), null, 2);
        } catch {}
      }
      $("#preview-text").textContent = text;
      return;
    }
    $(".preview-surface").hidden = false;
    $("#preview-text").hidden = true;
    $("#inspector-preview .hint").textContent =
      "Xem trước HTML/CSS tĩnh · JavaScript và tài nguyên ngoài chưa chạy.";
    try {
      const response = await apiFetch("/api/preview", {
        method: "POST",
        body: JSON.stringify({ files, entry }),
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.error);
      if (sequence === previewSequence)
        $("#product-preview").srcdoc = data.html;
    } catch (error) {
      if (sequence === previewSequence)
        $("#inspector-error").textContent = error.message;
    }
  }
  $("#refresh-preview").onclick = refreshPreview;
  $("#preview-entry").onchange = refreshPreview;
  $("#preview-mobile").onclick = () => {
    const mobile = $("#product-preview").classList.toggle("mobile-preview");
    $("#preview-mobile").setAttribute("aria-pressed", String(mobile));
  };

  function renderDocuments() {
    const root = $("#document-list"),
      choices = $("#document-choices");
    root.replaceChildren();
    choices.replaceChildren();
    const search = $("#document-search").value.trim().toLocaleLowerCase("vi");
    for (const item of documents) {
      if (item.title.toLocaleLowerCase("vi").includes(search)) {
        const button = el("button", item.title);
        button.className = "document-item";
        button.setAttribute("aria-current", String(documentId === item.id));
        button.append(
          el(
            "small",
            item.characters +
              " ký tự · " +
              new Date(item.updated).toLocaleDateString("vi-VN"),
          ),
        );
        button.onclick = () => openDocument(item.id);
        root.append(button);
      }
      const label = el("label", ""),
        checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = selectedDocuments.includes(item.id);
      checkbox.onchange = () => {
        if (checkbox.checked && selectedDocuments.length >= 5) {
          checkbox.checked = false;
          $("#draft-status").textContent = "Chọn tối đa 5 tài liệu.";
          return;
        }
        selectedDocuments = checkbox.checked
          ? [...selectedDocuments, item.id]
          : selectedDocuments.filter((id) => id !== item.id);
        persistDraft();
      };
      label.append(checkbox, document.createTextNode(item.title));
      choices.append(label);
    }
    if (!root.childElementCount)
      root.append(
        el(
          "p",
          documents.length
            ? "Không có tài liệu khớp từ khóa."
            : "Chưa có tài liệu. Thêm yêu cầu, ghi chú hoặc hướng dẫn cho đội.",
        ),
      );
    if (!documents.length)
      choices.append(el("p", "Chưa có tài liệu. Thêm tại mục Tài liệu."));
    $("#document-count").textContent =
      documents.length + "/30 tài liệu · tối đa 500 KB";
  }
  async function loadDocuments() {
    try {
      const response = await apiFetch("/api/documents");
      const data = await response.json();
      if (!response.ok) throw Error(data.error);
      documents = data.documents;
      const selected = selectedDocuments.filter((id) =>
        documents.some((item) => item.id === id),
      );
      if (selected.length !== selectedDocuments.length) {
        selectedDocuments = selected;
        persistDraft();
      }
      renderDocuments();
    } catch (error) {
      $("#document-status").textContent = error.message;
    }
  }
  function clearDocument() {
    documentSequence++;
    documentId = null;
    documentDirty = false;
    $("#document-form").reset();
    $("#document-heading").textContent = "Tài liệu mới";
    $("#delete-document").hidden = true;
    $("#document-status").textContent = "";
    renderDocuments();
  }
  async function openDocument(id) {
    if (
      documentSaving ||
      (documentDirty && !confirm("Bỏ thay đổi tài liệu chưa lưu?"))
    )
      return;
    const sequence = ++documentSequence,
      editVersion = documentEditVersion;
    try {
      const response = await apiFetch("/api/documents/" + id);
      const data = await response.json();
      if (!response.ok) throw Error(data.error);
      if (
        sequence !== documentSequence ||
        editVersion !== documentEditVersion ||
        documentSaving
      )
        return;
      documentId = data.id;
      documentDirty = false;
      $("#document-title").value = data.title;
      $("#document-content").value = data.content;
      $("#document-heading").textContent = "Chỉnh sửa tài liệu";
      $("#delete-document").hidden = false;
      $("#document-status").textContent = "";
      renderDocuments();
    } catch (error) {
      $("#document-status").textContent = error.message;
    }
  }
  $("#new-document").onclick = () => {
    if (
      !documentSaving &&
      (!documentDirty || confirm("Bỏ thay đổi tài liệu chưa lưu?"))
    ) {
      clearDocument();
      $("#document-title").focus();
    }
  };
  $("#document-search").oninput = renderDocuments;
  for (const id of ["document-title", "document-content"])
    $("#" + id).oninput = () => {
      documentDirty = true;
      documentEditVersion++;
    };
  $("#document-import").onchange = async () => {
    const file = $("#document-import").files[0];
    if (!file) return;
    try {
      if (file.size > 80000 || !/\.(txt|md|markdown|json)$/i.test(file.name))
        throw Error(
          "Chọn tệp TXT/Markdown/JSON UTF-8, tối đa 80 KB và 20000 ký tự.",
        );
      const content = new TextDecoder("utf-8", { fatal: true }).decode(
        await file.arrayBuffer(),
      );
      if (content.length > 20000 || !content.trim())
        throw Error("Nội dung phải từ 1 đến 20000 ký tự.");
      if (documentSaving) return;
      $("#document-title").value = file.name.slice(0, 100);
      $("#document-content").value = content;
      documentDirty = true;
      documentEditVersion++;
      $("#document-status").textContent =
        "Đã đọc tệp. Bấm Lưu tài liệu để thêm vào thư viện.";
    } catch (error) {
      $("#document-status").textContent = error.message;
    }
  };
  function lockDocument(busy) {
    documentSaving = busy;
    for (const id of [
      "save-document",
      "delete-document",
      "document-import",
      "document-title",
      "document-content",
    ])
      $("#" + id).disabled = busy;
  }
  $("#document-form").onsubmit = async (event) => {
    event.preventDefault();
    if (documentSaving) return;
    lockDocument(true);
    try {
      const response = await apiFetch("/api/documents", {
        method: "POST",
        body: JSON.stringify({
          id: documentId,
          title: $("#document-title").value,
          content: $("#document-content").value,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.error);
      documentId = data.id;
      documentDirty = false;
      $("#delete-document").hidden = false;
      $("#document-heading").textContent = "Chỉnh sửa tài liệu";
      $("#document-status").textContent =
        "Đã lưu. Khi giao việc, chọn tài liệu này trong phần đính kèm.";
      await loadDocuments();
    } catch (error) {
      $("#document-status").textContent = error.message;
    } finally {
      lockDocument(false);
    }
  };
  $("#delete-document").onclick = async () => {
    if (
      !documentId ||
      documentSaving ||
      !confirm(
        "Xóa tài liệu “" +
          $("#document-title").value +
          "” khỏi thư viện? Bản đã gửi trong lịch sử nhiệm vụ vẫn được giữ.",
      )
    )
      return;
    lockDocument(true);
    try {
      const response = await apiFetch(
        "/api/documents/" + documentId + "/delete",
        { method: "POST", body: JSON.stringify({ confirmation: documentId }) },
      );
      const data = await response.json();
      if (!response.ok) throw Error(data.error);
      clearDocument();
      await loadDocuments();
      $("#document-status").textContent = "Đã xóa tài liệu khỏi thư viện.";
    } catch (error) {
      $("#document-status").textContent = error.message;
    } finally {
      lockDocument(false);
    }
  };
  $("#clear-memory").onclick = () => {
    if (
      $("#save-memory").disabled ||
      !confirm(
        "Xóa bộ nhớ dự án chung? Bản đã gửi trong nhiệm vụ cũ vẫn được giữ.",
      )
    )
      return;
    $("#memory").value = "";
    $("#memory-form").requestSubmit();
  };
  window.addEventListener("workspace:documents", renderDocuments);

  async function loadBots(force = false) {
    if (botsLoading || (!force && bots.length && currentView !== "team"))
      return;
    botsLoading = true;
    try {
      const response = await apiFetch("/api/bots");
      const data = await response.json();
      if (!response.ok) throw Error(data.error);
      bots = data.bots;
      if (JSON.stringify(data) === botSignature) return;
      botSignature = JSON.stringify(data);
      const grid = $("#bot-grid");
      grid.replaceChildren();
      for (const bot of bots) {
        if (bot.kind === "expert") {
          const option = $("#expert option[value='" + bot.id + "']");
          if (option) option.textContent = "ECC · " + bot.name;
        }
        const card = el("article", "");
        card.className = "bot-card";
        card.dataset.botId = bot.id;
        const top = el("div", "");
        top.className = "bot-top";
        const avatar = el(
          "button",
          bot.kind === "manager" ? "◷" : bot.kind === "expert" ? "◈" : "◇",
        );
        avatar.className = "bot-avatar";
        avatar.type = "button";
        avatar.title = bot.configurable
          ? "Thiết lập " + bot.name
          : "Mở giới hạn tài nguyên";
        avatar.setAttribute("aria-label", avatar.title);
        avatar.onclick = () =>
          bot.configurable ? editBot(bot) : showView("resources");
        const kind = el(
          "span",
          {
            manager: "QUẢN LÝ",
            expert: "CHUYÊN GIA ECC",
            worker: "BOT THỰC THI",
          }[bot.kind],
        );
        kind.className = "bot-kind";
        top.append(avatar, kind);
        card.append(top, el("h3", bot.name), el("p", bot.description));
        if (bot.configurable) {
          card.append(
            el(
              "small",
              "Ollama: " +
                (bot.model_bindings?.ollama || "mặc định") +
                " · OpenAI: " +
                (bot.model_bindings?.ai || "mặc định"),
            ),
          );
        }
        if (bot.name !== bot.default_name)
          card.append(el("small", "Vai trò: " + bot.default_name));
        const current = data.active.filter(
          (task) =>
            bot.kind === "manager" ||
            task.stage.startsWith(
              bot.kind === "expert"
                ? "Chuyên gia ECC · " + bot.default_name
                : bot.default_name,
            ),
        );
        const status = el(
          "div",
          current.length
            ? "Đang làm: " +
                current
                  .map((task) => task.stage + " · " + task.prompt.slice(0, 140))
                  .join("; ")
            : bot.kind === "manager"
              ? "Sẵn sàng · quản lý bằng mã"
              : bot.kind === "expert"
                ? "Sẵn sàng khi được chọn"
                : "Rảnh · chờ bước được phân công",
        );
        status.className = "bot-status" + (current.length ? " busy" : "");
        card.append(status);
        if (bot.instructions)
          card.append(el("small", "Có hướng dẫn riêng cho nhiệm vụ mới"));
        const button = el(
          "button",
          bot.configurable ? "Thiết lập bot" : "Thiết lập giới hạn",
        );
        button.className = "secondary";
        button.onclick = () =>
          bot.configurable ? editBot(bot) : showView("resources");
        card.append(button);
        if (bot.kind === "expert") {
          const choose = el("button", "Giao việc cho chuyên gia này");
          choose.className = "secondary";
          choose.onclick = () => {
            showView("workspace");
            $("#expert").value = bot.id;
            $(".advanced-compose").open = true;
            persistDraft();
            $("#prompt").focus();
          };
          card.append(choose);
        }
        if (current.length) {
          const inspect = el("button", "Xem việc đang làm");
          inspect.className = "secondary";
          inspect.onclick = () => openTask(current[0].id);
          card.append(inspect);
        }
        grid.append(card);
      }
      $("#bots-status").textContent =
        "Thiết lập riêng áp dụng cho nhiệm vụ mới. Nhiệm vụ đang chạy giữ thiết lập lúc giao.";
    } catch (error) {
      $("#bots-status").textContent = error.message;
    } finally {
      botsLoading = false;
    }
  }
  async function editBot(bot) {
    editedBot = bot;
    $("#bot-dialog-title").textContent = "Thiết lập · " + bot.name;
    $("#bot-name").value = bot.name;
    $("#bot-instructions").value = bot.instructions;
    $("#bot-description").textContent = bot.description;
    $("#bot-save-status").textContent = "";
    $("#save-bot").disabled = true;
    $("#bot-dialog").showModal();
    try {
      await window.PlatformUI?.fillBindings(bot);
      $("#save-bot").disabled = false;
    } catch (error) {
      $("#bot-save-status").textContent = error.message;
    }
  }
  $("#close-bot").onclick = () => $("#bot-dialog").close();
  $("#reset-bot").onclick = () => {
    $("#bot-name").value = editedBot.default_name;
    $("#bot-instructions").value = "";
    $("#bot-model-ollama").value = "";
    $("#bot-model-ai").value = "";
  };
  $("#bot-form").onsubmit = async (event) => {
    event.preventDefault();
    $("#save-bot").disabled = true;
    try {
      const response = await apiFetch("/api/bots", {
        method: "POST",
        body: JSON.stringify({
          id: editedBot.id,
          name: $("#bot-name").value,
          instructions: $("#bot-instructions").value,
          model_bindings: {
            ollama: $("#bot-model-ollama").value,
            ai: $("#bot-model-ai").value,
          },
        }),
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.error);
      $("#bot-save-status").textContent = "Đã lưu thiết lập cho nhiệm vụ mới.";
      botSignature = "";
      await loadBots();
    } catch (error) {
      $("#bot-save-status").textContent = error.message;
    } finally {
      $("#save-bot").disabled = false;
    }
  };
  window.addEventListener("beforeunload", (event) => {
    if (editorDirty || documentDirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  window.WorkspaceUI = {
    showView,
    openTask,
    deletionWarning: (id) =>
      selectedTask?.id === id && editorDirty
        ? "Bản sửa tệp chưa lưu trong khung đang xem cũng sẽ được bỏ."
        : "",
    taskDeleted: (id) => {
      deletedTaskIds.add(id);
      if (selectedTask?.id === id) clearInspector(true);
    },
  };
  $("#sidebar-health").textContent = $("#health-status").textContent;
  showView(location.hash.slice(1));
  loadDocuments();
  loadBots();
  setInterval(loadBots, 4000);
})();
