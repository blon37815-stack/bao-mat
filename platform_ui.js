/* Stable settings for projects, model profiles and isolated product checks. */
(() => {
  const $ = (selector) => document.querySelector(selector);
  const el = (tag, text = "") => {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  };
  let data,
    selectedTask,
    workspaceSignature = "",
    checksBusy = false;
  const panel = el("details");
  panel.className = "panel";
  panel.open = true;
  panel.innerHTML = `<summary>Nền tảng bot, model và dự án</summary>
    <p id="platform-status" role="status"></p>
    <p>Lệnh đã nối vào ứng dụng: /plan yêu cầu, /python yêu cầu, /web yêu cầu, /data yêu cầu, /code-review mã-nhiệm-vụ, /verify mã-nhiệm-vụ. Các lệnh ECC khác sẽ báo chưa hỗ trợ.</p>
    <h3>Model dùng chung giữa các bot</h3>
    <p>Tạo hồ sơ rồi chọn trong Thiết lập bot. Không tự tải model, đổi nhà cung cấp hoặc mở lượt gọi đồng thời.</p>
    <select id="profile-picker" aria-label="Hồ sơ model để sửa"><option value="">Tạo hồ sơ mới</option></select>
    <form id="model-profile-form">
      <label for="profile-id">ID hồ sơ</label><input id="profile-id" required maxlength="64" pattern="[a-zA-Z0-9_-]+" placeholder="python-local"/>
      <label for="profile-name">Tên hiển thị</label><input id="profile-name" required maxlength="80"/>
      <label for="profile-provider">Nhà cung cấp</label><select id="profile-provider"><option value="ollama">Ollama trên máy</option><option value="ai">OpenAI · cần khóa, có thể tính phí</option></select>
      <label for="profile-model">Tên model đã có</label><input id="profile-model" required maxlength="200" placeholder="qwen3:4b"/>
      <label for="profile-timeout">Thời hạn mỗi lần gọi (giây)</label><input id="profile-timeout" type="number" min="1" max="7200" value="600" required/>
      <label for="profile-context">Context Ollama (token; 0 dùng mặc định dịch vụ)</label><input id="profile-context" type="number" min="0" max="32768" value="0" required/>
      <label for="profile-output">Giới hạn đầu ra (token)</label><input id="profile-output" type="number" min="128" max="16384" value="4096" required/>
      <label for="profile-input">Giới hạn đầu vào (ký tự, không phải token)</label><input id="profile-input" type="number" min="1000" max="200000" value="100000" required/>
      <button>Lưu hồ sơ model</button> <button type="button" id="delete-profile" class="secondary">Xóa hồ sơ riêng</button>
    </form>
    <p id="model-profile-status" role="status"></p>
    <h3>Dự án và bộ nhớ riêng</h3>
    <select id="project-picker" aria-label="Dự án để sửa"><option value="">Tạo dự án mới</option></select>
    <form id="project-profile-form">
      <label for="project-id">ID dự án</label><input id="project-id" maxlength="64" pattern="[a-zA-Z0-9_-]+" required/>
      <label for="project-name">Tên dự án</label><input id="project-name" maxlength="80" required/>
      <label for="project-memory">Bộ nhớ dự án</label><textarea id="project-memory" maxlength="8000"></textarea>
      <button>Lưu dự án</button>
    </form>
    <p id="project-profile-status" role="status"></p>
    <h3>Kiểm thử sản phẩm Python</h3>
    <p>Chạy unittest trong Docker Linux, mạng tắt và giới hạn tài nguyên. Web chưa có runner trình duyệt. Không chạy mã sản phẩm trực tiếp trên máy.</p>
    <button id="sandbox-health" class="secondary">Kiểm tra Docker</button>
    <p id="sandbox-health-status" role="status"></p>
    <form id="sandbox-policy-form"><label><input id="sandbox-auto" type="checkbox"/> Tự kiểm thử trong Docker khi đội kiểm tra sản phẩm mới</label><button>Lưu chế độ kiểm thử</button></form>
    <p id="sandbox-policy-status" role="status"></p>`;
  $("#view-settings").prepend(panel);

  const projectLabel = el("label", "Dự án nhận công việc");
  projectLabel.htmlFor = "task-project";
  const project = el("select");
  project.id = "task-project";
  project.append(new Option("Dự án chung", "default"));
  $("#prompt").before(projectLabel, project);
  const filter = el("select");
  filter.id = "project-filter";
  filter.setAttribute("aria-label", "Lọc theo dự án");
  filter.append(new Option("Tất cả dự án", ""));
  $("#filter").after(filter);
  filter.onchange = () => {
    pageOffset = 0;
    refresh();
  };
  project.onchange = () => {
    selectedProject = project.value;
    persistDraft();
  };

  const workspace = el("details");
  workspace.id = "run-workspace";
  workspace.innerHTML = `<summary>Cấu hình và kiểm thử của công việc</summary><pre id="run-config"></pre>
    <button id="run-product-tests" class="secondary">Chạy kiểm thử Python (Docker)</button>
    <p id="run-tests-status" role="status"></p><pre id="run-checks-output"></pre>`;
  $("#inspector-status").after(workspace);

  async function request(path, body) {
    const response = await apiFetch(
      path,
      body === undefined ? {} : { method: "POST", body: JSON.stringify(body) },
    );
    const result = await response.json();
    if (!response.ok) throw Error(result.error || "Không hoàn tất yêu cầu");
    return result;
  }
  function options(select, items, empty, value) {
    select.replaceChildren(new Option(empty, ""));
    for (const item of items) select.append(new Option(item.name, item.id));
    select.value = value || "";
  }
  async function load() {
    data = await request("/api/platform");
    if (data.api_version !== 1)
      throw Error(
        "Giao diện và API khác phiên bản; cập nhật đồng bộ rồi làm mới trang",
      );
    $("#platform-status").textContent =
      `API ${data.api_version} · Dữ liệu ${data.schema_version} · ${data.models.length} hồ sơ model · chạy lần lượt`;
    options(
      $("#profile-picker"),
      data.models.filter((item) => !item.builtin),
      "Tạo hồ sơ mới",
      $("#profile-picker").value,
    );
    options(
      $("#project-picker"),
      data.projects,
      "Tạo dự án mới",
      $("#project-picker").value,
    );
    const previous = selectedProject;
    project.replaceChildren(
      ...data.projects.map((item) => new Option(item.name, item.id)),
    );
    project.value = data.projects.some((item) => item.id === previous)
      ? previous
      : "default";
    selectedProject = project.value;
    options(filter, data.projects, "Tất cả dự án", filter.value);
    $("#sandbox-auto").checked = data.sandbox_enabled;
  }
  $("#profile-picker").onchange = () => {
    const value = data.models.find(
      (item) => item.id === $("#profile-picker").value,
    );
    const fields = {
      id: "id",
      name: "name",
      provider: "provider",
      model: "model",
      timeout: "timeout_seconds",
      context: "context_tokens",
      output: "max_output_tokens",
      input: "max_input_chars",
    };
    if (!value) {
      $("#model-profile-form").reset();
      return;
    }
    for (const [field, key] of Object.entries(fields))
      $("#profile-" + field).value = value[key];
  };
  $("#model-profile-form").onsubmit = async (event) => {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    try {
      const saved = await request("/api/models", {
        id: $("#profile-id").value,
        name: $("#profile-name").value,
        provider: $("#profile-provider").value,
        model: $("#profile-model").value,
        timeout_seconds: Number($("#profile-timeout").value),
        context_tokens: Number($("#profile-context").value),
        max_output_tokens: Number($("#profile-output").value),
        max_input_chars: Number($("#profile-input").value),
      });
      $("#model-profile-status").textContent =
        `Đã lưu phiên bản ${saved.revision}. Chọn hồ sơ trong Thiết lập bot; chưa kiểm chứng suy luận model này.`;
      await load();
    } catch (error) {
      $("#model-profile-status").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  };
  $("#delete-profile").onclick = async () => {
    const id = $("#profile-picker").value;
    if (
      !id ||
      !confirm("Xóa hồ sơ model này? Cấu hình trong nhiệm vụ cũ vẫn giữ.")
    )
      return;
    try {
      await request("/api/models/delete", { id });
      await load();
      $("#model-profile-form").reset();
      $("#model-profile-status").textContent = "Đã xóa hồ sơ riêng.";
    } catch (error) {
      $("#model-profile-status").textContent = error.message;
    }
  };
  $("#project-picker").onchange = () => {
    const value = data.projects.find(
      (item) => item.id === $("#project-picker").value,
    );
    if (!value) {
      $("#project-profile-form").reset();
      return;
    }
    $("#project-id").value = value.id;
    $("#project-name").value = value.name;
    $("#project-memory").value = value.memory;
  };
  $("#project-profile-form").onsubmit = async (event) => {
    event.preventDefault();
    try {
      await request("/api/projects", {
        id: $("#project-id").value,
        name: $("#project-name").value,
        memory: $("#project-memory").value,
      });
      await load();
      $("#project-profile-status").textContent =
        "Đã lưu dự án; chọn dự án khi giao việc.";
    } catch (error) {
      $("#project-profile-status").textContent = error.message;
    }
  };
  $("#sandbox-health").onclick = async () => {
    $("#sandbox-health").disabled = true;
    try {
      const result = await request("/api/sandbox");
      $("#sandbox-health-status").textContent =
        result.message + " · " + result.image;
    } catch (error) {
      $("#sandbox-health-status").textContent = error.message;
    } finally {
      $("#sandbox-health").disabled = false;
    }
  };
  $("#sandbox-policy-form").onsubmit = async (event) => {
    event.preventDefault();
    try {
      await request("/api/sandbox-policy", {
        enabled: $("#sandbox-auto").checked,
      });
      $("#sandbox-policy-status").textContent =
        "Đã lưu cho nhiệm vụ mới. Thiếu Docker hoặc loại tệp chưa hỗ trợ sẽ ghi rõ chưa kiểm thử.";
    } catch (error) {
      $("#sandbox-policy-status").textContent = error.message;
    }
  };
  async function loadChecks(id) {
    const value = await request("/api/tasks/" + id + "/workspace");
    if (selectedTask?.id !== id) return;
    const last = value.checks.at(-1);
    $("#run-checks-output").textContent = last
      ? `${last.status} · ${last.tests || 0} kiểm thử\n${last.output || ""}`
      : "Chưa có kết quả kiểm thử chức năng.";
  }
  window.addEventListener("workspace:task", async ({ detail }) => {
    selectedTask = detail;
    const runtime = detail.runtime;
    const signature = detail.id + JSON.stringify(runtime) + detail.status;
    $("#run-product-tests").disabled =
      checksBusy ||
      !detail.product ||
      detail.mode === "demo" ||
      ["queued", "running"].includes(detail.status);
    if (signature === workspaceSignature) return;
    workspaceSignature = signature;
    const lines =
      runtime?.legacy || !runtime
        ? ["Nhiệm vụ cũ chưa ghi cấu hình model."]
        : [
            "Workspace: " + runtime.project_id + "/" + detail.id,
            "Tệp và cấu hình lưu trong SQLite; vùng kiểm thử Docker dùng thư mục tạm riêng.",
            ...Object.entries(runtime.models).map(
              ([role, model]) =>
                `${role}: ${model.provider} · ${model.model} · hồ sơ ${model.id} v${model.revision}`,
            ),
            "Tự kiểm thử Docker: " + (runtime.sandbox_enabled ? "bật" : "tắt"),
            runtime.expert_source
              ? "Hướng dẫn ECC: " + runtime.expert_source.commit.slice(0, 12)
              : "Không có bản chụp hướng dẫn ECC.",
          ];
    $("#run-config").textContent = lines.join("\n");
    try {
      await loadChecks(detail.id);
    } catch (error) {
      $("#run-tests-status").textContent = error.message;
    }
  });
  $("#run-product-tests").onclick = async () => {
    if (!selectedTask) return;
    const id = selectedTask.id;
    checksBusy = true;
    $("#run-product-tests").disabled = true;
    $("#run-tests-status").textContent = "Đang kiểm thử trong Docker…";
    try {
      const report = await request("/api/tasks/" + id + "/run-tests", {});
      if (selectedTask?.id === id) {
        $("#run-tests-status").textContent = "Kết quả: " + report.status;
        await loadChecks(id);
      }
    } catch (error) {
      $("#run-tests-status").textContent = error.message;
    } finally {
      checksBusy = false;
      $("#run-product-tests").disabled =
        !selectedTask?.product ||
        selectedTask.mode === "demo" ||
        ["queued", "running"].includes(selectedTask.status);
    }
  };
  window.addEventListener("workspace:view", ({ detail }) => {
    if (["settings", "team"].includes(detail.name))
      load().catch((error) => {
        $("#platform-status").textContent = error.message;
      });
  });
  window.PlatformUI = {
    async fillBindings(bot) {
      const result = await request("/api/platform");
      for (const provider of ["ollama", "ai"])
        options(
          $("#bot-model-" + provider),
          result.models.filter((item) => item.provider === provider),
          "Theo mặc định",
          bot.model_bindings?.[provider],
        );
    },
  };
  load().catch((error) => {
    $("#platform-status").textContent = error.message;
  });
})();
