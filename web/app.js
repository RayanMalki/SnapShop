const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const startBtn = document.getElementById("startBtn");
const captureBtn = document.getElementById("captureBtn");
const fileBtn = document.getElementById("fileBtn");
const fileInput = document.getElementById("fileInput");
const apiBaseInput = document.getElementById("apiBase");
const resultEl = document.getElementById("result");
const resultBody = document.getElementById("resultBody");

let stream = null;

function apiBase() {
  return apiBaseInput.value.replace(/\/$/, "");
}

// --- Auth / session ---------------------------------------------------------
const TOKEN_KEY = "snapshop.token";
const USER_KEY = "snapshop.user";

function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}
function authHeaders() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function authRequest(path, email, password) {
  const res = await fetch(`${apiBase()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Authentication failed");
  localStorage.setItem(TOKEN_KEY, data.token);
  localStorage.setItem(USER_KEY, data.user_id || email);
  updateAuthUI();
}

async function signIn(email, password) {
  await authRequest("/auth/login", email, password);
}

async function signUp(email, password) {
  await authRequest("/auth/signup", email, password);
}

function signOut() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  document.getElementById("history").hidden = true;
  updateAuthUI();
}

function updateAuthUI() {
  const loggedIn = !!getToken();
  document.getElementById("loggedOut").hidden = loggedIn;
  document.getElementById("loggedIn").hidden = !loggedIn;
  if (loggedIn) {
    document.getElementById("userLabel").textContent =
      "Signed in as " + (localStorage.getItem(USER_KEY) || "user");
  }
}

async function startCamera() {
  stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: "environment" },
    audio: false,
  });
  video.srcObject = stream;
  captureBtn.disabled = false;
  startBtn.textContent = "Camera on";
  startBtn.disabled = true;
}

function canvasToBlob() {
  const w = video.videoWidth;
  const h = video.videoHeight;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, w, h);
  return new Promise((resolve) => {
    canvas.toBlob(resolve, "image/jpeg", 0.92);
  });
}

function showLoading() {
  resultEl.classList.add("visible");
  resultBody.className = "skeleton";
  resultBody.textContent = "Scanning… (Gemini + UCP, may take a few seconds)";
}

function renderResult(data) {
  if (data.status === "processing") {
    resultBody.className = "skeleton";
    resultBody.textContent = "Still processing…";
    return;
  }
  if (data.status === "error") {
    resultBody.className = "";
    resultBody.textContent = data.error || "Scan failed";
    return;
  }
  const p = data.product;
  const price = (p.price_min / 100).toFixed(2);
  const siteUrl = p.merchant_url || (p.merchant_domain ? `https://${p.merchant_domain}` : "");
  const isSimilar = (data.match_quality || "similar") !== "exact";

  // No badge when it's an exact match (silence = confidence). Only warn when
  // we're NOT sure about the match.
  const banner = isSimilar
    ? `<div style="background:#3b2f1a;border:1px solid #a16207;color:#fde68a;padding:.6rem .8rem;border-radius:8px;margin-bottom:.9rem;font-size:.85rem;line-height:1.35;">
         ⚠️ <strong>Not sure this is your exact product.</strong><br/>Here is the closest match we found.
       </div>`
    : "";

  const alts = (data.alternatives || [])
    .map((a) => {
      const ap = (a.price_min / 100).toFixed(2);
      const aurl = a.checkout_url || a.merchant_url || (a.merchant_domain ? `https://${a.merchant_domain}` : "#");
      return `
        <a href="${aurl}" target="_blank" rel="noopener" style="display:flex;gap:.6rem;align-items:center;padding:.45rem;border-radius:8px;text-decoration:none;color:inherit;background:#1f1f23;">
          <img src="${a.image_url}" alt="" style="width:42px;height:42px;border-radius:6px;object-fit:cover;float:none;margin:0;" />
          <span style="flex:1;min-width:0;">
            <span style="display:block;font-size:.8rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${a.title}</span>
            <span style="display:block;font-size:.75rem;color:#a1a1aa;">$${ap} ${a.currency} · ${a.merchant_domain}</span>
          </span>
        </a>`;
    })
    .join("");

  const altsBlock = alts
    ? `<div style="margin-top:1rem;">
         <div style="font-size:.8rem;color:#a1a1aa;margin-bottom:.45rem;">${isSimilar ? "Other similar results" : "Alternatives"}</div>
         <div style="display:flex;flex-direction:column;gap:.4rem;">${alts}</div>
       </div>`
    : "";

  resultBody.className = "";
  resultBody.innerHTML = `
    ${banner}
    <img src="${p.image_url}" alt="" />
    <strong>${p.title}</strong><br />
    <span>$${price} ${p.currency}</span><br />
    <span>${p.merchant_domain}</span><br />
    <em>${data.vision_summary || ""}</em>
    <br clear="all" />
    <div class="links">
      ${data.continue_url ? `<a class="store" href="${data.continue_url}" target="_blank" rel="noopener">Checkout →</a>` : ""}
      ${siteUrl ? `<a class="site" href="${siteUrl}" target="_blank" rel="noopener">Visit site →</a>` : ""}
    </div>
    ${altsBlock}
  `;
}

async function postScan(blob, filename = "capture.jpg") {
  showLoading();
  const form = new FormData();
  form.append("file", blob, filename);
  const res = await fetch(`${apiBase()}/scan`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

async function runScan(blob, filename) {
  try {
    const data = await postScan(blob, filename);
    renderResult(data);
  } catch (err) {
    resultEl.classList.add("visible");
    resultBody.className = "";
    resultBody.textContent = err.message || String(err);
  }
}

startBtn.addEventListener("click", () => {
  startCamera().catch((e) => alert(e.message));
});

captureBtn.addEventListener("click", async () => {
  captureBtn.disabled = true;
  try {
    const blob = await canvasToBlob();
    await runScan(blob);
  } finally {
    captureBtn.disabled = false;
  }
});

fileBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  await runScan(file, file.name);
  fileInput.value = "";
});

// --- History ("My finds") --------------------------------------------------
async function loadHistory() {
  const body = document.getElementById("historyBody");
  body.textContent = "Loading…";
  try {
    const res = await fetch(`${apiBase()}/history`, { headers: authHeaders() });
    const items = await res.json();
    if (!Array.isArray(items) || items.length === 0) {
      body.textContent = "No finds yet.";
      return;
    }
    body.innerHTML = items
      .map((s) => {
        const p = s.product;
        if (!p) return "";
        const price = (p.price_min / 100).toFixed(2);
        const url =
          s.continue_url ||
          p.checkout_url ||
          p.merchant_url ||
          (p.merchant_domain ? `https://${p.merchant_domain}` : "#");
        return `
          <a class="histRow" href="${url}" target="_blank" rel="noopener">
            <img src="${p.image_url}" alt="" />
            <span style="flex:1;min-width:0;">
              <span style="display:block;font-size:.85rem;font-weight:600;color:#f4f4f5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${p.title}</span>
              <span style="display:block;font-size:.75rem;">$${price} ${p.currency} · ${p.merchant_domain}</span>
            </span>
          </a>`;
      })
      .join("");
  } catch (e) {
    body.textContent = "Couldn't load history.";
  }
}

// --- Auth wiring ------------------------------------------------------------
function credsOrAlert() {
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;
  if (!email || !password) {
    alert("Enter an email and password");
    return null;
  }
  return { email, password };
}

document.getElementById("signinBtn").addEventListener("click", async () => {
  const c = credsOrAlert();
  if (!c) return;
  try {
    await signIn(c.email, c.password);
  } catch (e) {
    alert(e.message || "Sign-in failed");
  }
});

document.getElementById("signupBtn").addEventListener("click", async () => {
  const c = credsOrAlert();
  if (!c) return;
  try {
    await signUp(c.email, c.password);
  } catch (e) {
    alert(e.message || "Sign-up failed");
  }
});

document.getElementById("logoutBtn").addEventListener("click", signOut);

document.getElementById("findsBtn").addEventListener("click", async () => {
  const h = document.getElementById("history");
  h.hidden = !h.hidden;
  if (!h.hidden) await loadHistory();
});

updateAuthUI();
