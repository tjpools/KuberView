const $ = (sel) => document.querySelector(sel);

let currentTab = "pods";
let currentNs = "";

const badge = (text, cls) => `<span class="badge ${cls}">${text}</span>`;

const phaseBadge = (phase) => {
  const cls = { Running: "ok", Succeeded: "ok", Pending: "warn", Failed: "err", Unknown: "err" }[phase] || "warn";
  return badge(phase, cls);
};

const readyBadge = (ready) => {
  const [a, b] = ready.split("/");
  return badge(ready, a === b ? "ok" : "warn");
};

const columns = {
  pods: ["Name", "Namespace", "Ready", "Status", "Restarts", "IP", "Node", "Age"],
  deployments: ["Name", "Namespace", "Ready", "Up-to-date", "Available", "Images", "Age"],
  services: ["Name", "Namespace", "Type", "Cluster IP", "Ports", "Age"],
  nodes: ["Name", "Ready", "Roles", "Version", "OS", "CPU", "Memory", "Age"],
  events: ["Age", "Type", "Reason", "Object", "Namespace", "Message"],
};

const rowRenderers = {
  pods: (p) => `
    <tr class="clickable" onclick="showLogs('${p.namespace}', '${p.name}')">
      <td>${p.name}</td><td>${p.namespace}</td><td>${readyBadge(p.ready)}</td>
      <td>${phaseBadge(p.phase)}</td><td>${p.restarts}</td>
      <td>${p.ip ?? ""}</td><td>${p.node ?? ""}</td><td>${p.age}</td>
    </tr>`,
  deployments: (d) => `
    <tr>
      <td>${d.name}</td><td>${d.namespace}</td><td>${readyBadge(d.ready)}</td>
      <td>${d.upToDate}</td><td>${d.available}</td>
      <td>${d.images.join(", ")}</td><td>${d.age}</td>
    </tr>`,
  services: (s) => `
    <tr>
      <td>${s.name}</td><td>${s.namespace}</td><td>${s.type}</td>
      <td>${s.clusterIP}</td><td>${s.ports.join(", ")}</td><td>${s.age}</td>
    </tr>`,
  nodes: (n) => `
    <tr>
      <td>${n.name}</td><td>${badge(n.ready === "True" ? "Ready" : "NotReady", n.ready === "True" ? "ok" : "err")}</td>
      <td>${n.roles.join(", ")}</td><td>${n.version}</td><td>${n.os}</td>
      <td>${n.cpu}</td><td>${n.memory}</td><td>${n.age}</td>
    </tr>`,
  events: (e) => `
    <tr>
      <td>${e.age}</td><td>${badge(e.type, e.type === "Normal" ? "ok" : "warn")}</td>
      <td>${e.reason}</td><td>${e.object}</td><td>${e.namespace}</td><td>${e.message}</td>
    </tr>`,
};

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function refresh() {
  try {
    const nsParam = currentNs ? `?namespace=${currentNs}` : "";
    const endpoint = currentTab === "nodes" ? "/api/nodes" : `/api/${currentTab}${nsParam}`;
    const [data, overview] = await Promise.all([fetchJSON(endpoint), fetchJSON("/api/overview")]);

    $("#thead").innerHTML = `<tr>${columns[currentTab].map((c) => `<th>${c}</th>`).join("")}</tr>`;
    $("#tbody").innerHTML = data.map(rowRenderers[currentTab]).join("");

    $("#overview").innerHTML = [
      ["nodes", overview.nodes],
      ["namespaces", overview.namespaces],
      ["pods", overview.pods],
      ["deployments", overview.deployments],
      ["services", overview.services],
    ].map(([k, v]) => `<span class="stat"><b>${v}</b>${k}</span>`).join("");

    $("#status").textContent = `last update ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    $("#status").textContent = `error: ${err.message}`;
  }
}

async function loadNamespaces() {
  const list = await fetchJSON("/api/namespaces");
  const sel = $("#namespace");
  const prev = sel.value;
  sel.innerHTML =
    `<option value="">all</option>` +
    list.map((ns) => `<option value="${ns.name}">${ns.name}</option>`).join("");
  sel.value = prev;
}

window.showLogs = async (namespace, name) => {
  $("#logs-title").textContent = `${namespace}/${name}`;
  $("#logs-body").textContent = "loading…";
  $("#logs-dialog").showModal();
  try {
    const data = await fetchJSON(`/api/pods/${namespace}/${name}/logs?tail=200`);
    $("#logs-body").textContent = data.logs || "(no logs)";
  } catch (err) {
    $("#logs-body").textContent = `failed to fetch logs: ${err.message}`;
  }
};

$("#logs-close").addEventListener("click", () => $("#logs-dialog").close());

document.querySelectorAll("nav button").forEach((btn) =>
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentTab = btn.dataset.tab;
    refresh();
  })
);

$("#namespace").addEventListener("change", (e) => {
  currentNs = e.target.value;
  refresh();
});

loadNamespaces();
refresh();
setInterval(refresh, 5000);
setInterval(loadNamespaces, 30000);
