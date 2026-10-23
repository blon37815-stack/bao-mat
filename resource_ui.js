// Loaded after app.js: uses its protected API client and task refresh functions.
let resourcesLoading = false,
  resourcePolicyLoaded = false;
async function refreshResources() {
  if (
    resourcesLoading ||
    (resourcePolicyLoaded && document.querySelector("#view-resources").hidden)
  )
    return;
  resourcesLoading = true;
  try {
    const response = await apiFetch("/api/resources");
    if (!response.ok)
      throw Error(
        "Chưa đọc được tài nguyên; kiểm tra phiên bản app đang chạy.",
      );
    const data = await response.json(),
      host = data.host;
    document.querySelector("#resource-cpu").textContent =
      host.cpu_percent === null
        ? "Đang lấy mẫu CPU…"
        : host.cpu_percent.toFixed(1) + "%";
    const gib = (bytes) => (bytes / 1024 ** 3).toFixed(1);
    document.querySelector("#resource-memory").textContent = host.memory
      ? host.memory.percent.toFixed(1) +
        "% · còn " +
        gib(host.memory.available_bytes) +
        "/" +
        gib(host.memory.total_bytes) +
        " GiB"
      : "Chưa đọc được RAM";
    document.querySelector("#resource-gpu").textContent =
      host.gpu.status === "ready"
        ? host.gpu.devices
            .map(
              (gpu) =>
                gpu.name +
                " · " +
                (gpu.percent === null ? "chưa có % tải" : gpu.percent + "%") +
                " · " +
                gpu.used_mb +
                "/" +
                gpu.total_mb +
                " MiB",
            )
            .join("; ")
        : host.gpu.message;
    document.querySelector("#resource-scope").textContent =
      host.scope +
      " Giới hạn lượt gọi/hàng đợi không phải giới hạn cứng CPU/RAM/GPU. Lấy mẫu: " +
      new Date(host.sampled_at).toLocaleTimeString("vi-VN");
    document.querySelector("#resource-active").textContent = data.active.length
      ? data.active
          .map(
            (task) =>
              (expertNames[task.expert] || task.expert) +
              " → " +
              task.stage +
              " · " +
              task.calls +
              "/" +
              task.call_limit +
              " lượt",
          )
          .join("; ")
      : "Chưa có nhiệm vụ đang chạy · tối đa 1 việc mỗi lúc";
    if (!resourcePolicyLoaded) {
      document.querySelector("#default-call-limit").value =
        data.policy.default_call_limit;
      document.querySelector("#max-waiting").value = data.policy.max_waiting;
      resourcePolicyLoaded = true;
    }
    if (!budgetTouched)
      document.querySelector("#call-limit").value =
        data.policy.default_call_limit;
  } catch (error) {
    document.querySelector("#resource-status").textContent = error.message;
  } finally {
    resourcesLoading = false;
  }
}
document.querySelector("#resource-form").onsubmit = async (event) => {
  event.preventDefault();
  const button = document.querySelector("#save-resources"),
    status = document.querySelector("#resource-status");
  button.disabled = true;
  try {
    const response = await apiFetch("/api/resource-policy", {
      method: "POST",
      body: JSON.stringify({
        default_call_limit: Number(
          document.querySelector("#default-call-limit").value,
        ),
        max_waiting: Number(document.querySelector("#max-waiting").value),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error);
    status.textContent =
      "Đã lưu. Lượt gọi mặc định áp dụng cho nhiệm vụ mới; giới hạn riêng của nhiệm vụ cũ được giữ.";
    await refreshResources();
    await refresh();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
};
refreshResources();
window.addEventListener("workspace:view", (event) => {
  if (event.detail.name === "resources") refreshResources();
});
setInterval(refreshResources, 2500);
