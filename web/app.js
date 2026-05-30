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
  resultBody.className = "";
  resultBody.innerHTML = `
    <img src="${p.image_url}" alt="" />
    <strong>${p.title}</strong><br />
    <span>$${price} ${p.currency}</span><br />
    <span>${p.merchant_domain}</span><br />
    <em>${data.vision_summary || ""}</em>
    <br clear="all" />
    <a class="store" href="${data.continue_url}" target="_blank" rel="noopener">
      Go to store →
    </a>
  `;
}

async function postScan(blob, filename = "capture.jpg") {
  showLoading();
  const form = new FormData();
  form.append("file", blob, filename);
  const res = await fetch(`${apiBase()}/scan`, { method: "POST", body: form });
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
