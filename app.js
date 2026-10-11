// Digital Risk Shield frontend. Talks only to /api/* (no secrets live here).
const $ = (s, r = document) => r.querySelector(s);
let status = null, brand = null;

// Build DOM safely: text is always set with textContent, never innerHTML.
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) k === "class" ? (n.className = v) : n.setAttribute(k, v);
  kids.flat().forEach(k => n.append(k instanceof Node ? k : document.createTextNode(k)));
  return n;
}

async function api(path, method = "GET", body) {
  let res;
  try {
    res = await fetch("/api" + path, { method, headers: { "Content-Type": "application/json" }, body: body && JSON.stringify(body) });
  } catch { throw new Error("Cannot reach the server. Is it running?"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Please check the form and try again.");
  return data;
}

function toast(msg, ok = false) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast" + (ok ? " ok" : ""); t.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => (t.hidden = true), 6000);
}

// ---- Routing -------------------------------------------------------------------
function route() {
  const name = (location.hash || "#dashboard").slice(1);
  const view = $("#view-" + name) ? name : "dashboard";
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("show", v.id === "view-" + view));
  document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("active", a.hash === "#" + view));
  if (view === "dashboard") loadDashboard();
}

// ---- Dashboard -----------------------------------------------------------------
const fmt = iso => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

async function loadDashboard() {
  try {
    const d = await api("/dashboard");
    const s = d.stats;
    $("#stats").replaceChildren(
      ...[["Total scans", s.total_scans], ["High-risk findings", s.high_risk, "hot"],
          ["Social profile scans", s.social_scans], ["Mobile app scans", s.app_scans]]
        .map(([label, n, cls]) => el("div", { class: "stat " + (cls || "") }, el("b", {}, String(n)), el("span", {}, label))));
    $("#history").replaceChildren(...d.recent.map(r => el("tr", {},
      el("td", {}, fmt(r.created_at)),
      el("td", { class: "id" }, r.submitted_identifier, r.fictional_demo ? el("span", { class: "tag" }, "fictional demo") : ""),
      el("td", {}, r.scan_type === "social" ? "Social" : "App"),
      el("td", {}, String(r.risk_score)),
      el("td", {}, el("span", { class: "pill " + r.risk_level }, r.risk_level)))));
    $("#empty").hidden = d.recent.length > 0;
  } catch (e) { toast(e.message); }
}

$("#load-demo").onclick = async () => {
  try { brand = (await api("/brand/demo", "POST")).brand; fillForms(); toast("Fictional NovaPay demo brand loaded.", true); } catch (e) { toast(e.message); }
};

// ---- Result card ---------------------------------------------------------------
function showResult(box, r, formEl) {
  const color = { Low: "--low", Medium: "--medium", High: "--high", Critical: "--critical" }[r.risk_level];
  const ring = el("div", { class: "ring", style: `--c:var(${color});--p:${r.risk_score}` }, el("div", {}, el("b", {}, String(r.risk_score)), el("span", {}, "of 100")));
  const body = el("div", {},
    el("h2", {}, el("span", { class: "pill " + r.risk_level }, r.risk_level + " risk"), "  " + r.verdict),
    el("p", { class: "muted" }, `Checked: ${r.identified}` + (r.platform ? ` on ${r.platform}` : "")),
    el("ul", {}, r.reasons.map(x => el("li", {}, x))),
    el("p", { class: "rec" }, "Recommendation: " + r.recommendation),
    el("p", { class: "muted note" }, r.stored_in === "demo"
      ? "Saved to demo memory only. It will be lost when the server restarts." : "Saved to your Supabase database."),
    r.fictional_demo ? el("p", { class: "muted note" }, "Fictional example brand. Not a threat found on the internet.") : "",
    el("button", { class: "btn", type: "button" }, "Scan another"));
  body.querySelector("button").onclick = () => { formEl.reset(); fillForms(); box.replaceChildren(); formEl.querySelector("[name=submitted]").focus(); };
  box.replaceChildren(el("div", { class: "panel result" }, ring, body));
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function wireScan(type, buildBody) {
  const form = $("#form-" + type), box = $("#result-" + type), btn = form.querySelector("button[type=submit]");
  form.onsubmit = async e => {
    e.preventDefault();
    btn.disabled = true; btn.replaceChildren(el("span", { class: "spin" }), "Scanning...");
    try {
      showResult(box, await api("/scan/" + type, "POST", buildBody(Object.fromEntries(new FormData(form)))), form);
      toast("Scan complete and saved.", true);
    } catch (err) { toast(err.message); }
    btn.disabled = false; btn.textContent = type === "social" ? "Scan profile" : "Scan app";
  };
}
wireScan("social", f => f);
wireScan("app", f => f);

// ---- Sample cases (fictional NovaPay) -----------------------------------------------
const SAMPLES = {
  social: [["Official account", { submitted: "novapay_official", platform: "Instagram" }],
           ["Look-alike: support24", { submitted: "novapay_support24", platform: "Instagram" }],
           ["Look-alike: rewards", { submitted: "nova_pay_rewards", platform: "X", description: "Claim your reward now! DM us." }]],
  app: [["Official app", { submitted: "NovaPay Wallet", publisher: "NovaPay Technologies Ltd" }],
        ["Similar name, unknown publisher", { submitted: "NovaPay Wallet Pro", publisher: "" }]],
};
document.querySelectorAll(".samples").forEach(box => {
  const type = box.dataset.for;
  box.append("Try fictional NovaPay samples (load the demo brand first):");
  SAMPLES[type].forEach(([label, vals]) => {
    const b = el("button", { class: "chip", type: "button" }, label);
    b.onclick = () => {
      const f = $("#form-" + type);
      f.reset(); f.brand_name.value = "NovaPay";
      Object.entries(vals).forEach(([k, v]) => (f[k].value = v));
    };
    box.append(b);
  });
});

// ---- Brand setup ---------------------------------------------------------------
function fillForms() {
  ["social", "app"].forEach(t => { const f = $("#form-" + t); if (!f.brand_name.value) f.brand_name.value = brand ? brand.name : ""; });
  const f = $("#form-brand");
  if (brand) {
    f.name.value = brand.name; f.official_website.value = brand.official_website;
    f.socials.value = brand.socials.join(", ");
    f.app_name.value = brand.apps[0]?.name || ""; f.app_publisher.value = brand.apps[0]?.publisher || "";
  }
}
$("#form-brand").onsubmit = async e => {
  e.preventDefault();
  const f = e.target;
  const apps = f.app_name.value.trim() ? [{ name: f.app_name.value, publisher: f.app_publisher.value }] : [];
  try {
    brand = (await api("/brand", "PUT", { name: f.name.value, official_website: f.official_website.value,
      socials: f.socials.value.split(",").map(s => s.trim()).filter(Boolean), apps })).brand;
    ["social", "app"].forEach(t => ($("#form-" + t).brand_name.value = brand.name));
    toast("Brand profile saved.", true);
  } catch (err) { toast(err.message); }
};

// ---- Start ---------------------------------------------------------------------
(async function init() {
  try {
    status = await api("/status");
    const b = $("#banner");
    b.className = "banner " + (status.mode === "demo" ? "demo" : "live");
    b.textContent = status.message;
    const sel = $("#form-social").platform;
    status.platforms.forEach(p => sel.append(el("option", {}, p)));
    brand = (await api("/brand")).brand;
    fillForms();
  } catch (e) { toast(e.message); }
  window.addEventListener("hashchange", route); route();
})();
