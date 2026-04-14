// SwiftGet Popup Script

const statusDot = document.getElementById("statusDot");
const statusLabel = document.getElementById("statusLabel");
const connStatus = document.getElementById("connStatus");
const urlInput = document.getElementById("urlInput");
const addBtn = document.getElementById("addBtn");
const focusBtn = document.getElementById("focusBtn");
const toast = document.getElementById("toast");

function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2000);
}

function setConnected(connected) {
  if (connected) {
    statusDot.classList.add("connected");
    statusLabel.textContent = "연결됨";
    connStatus.textContent = "활성";
  } else {
    statusDot.classList.remove("connected");
    statusLabel.textContent = "연결 안 됨";
    connStatus.textContent = "비활성";
  }
}

// Check native app connection status
browser.runtime.sendMessage({ action: "getStatus" }).then(resp => {
  setConnected(resp?.connected || false);
}).catch(() => setConnected(false));

addBtn.addEventListener("click", () => {
  const url = urlInput.value.trim();
  if (!url || !url.startsWith("http")) {
    showToast("올바른 URL을 입력하세요");
    return;
  }
  browser.runtime.sendMessage({ action: "manualDownload", url }).then(() => {
    showToast("SwiftGet으로 전송됨!");
    urlInput.value = "";
  });
});

focusBtn.addEventListener("click", () => {
  browser.runtime.sendMessage({ action: "focusApp" });
  showToast("앱 활성화 요청 전송");
});

urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") addBtn.click();
});
