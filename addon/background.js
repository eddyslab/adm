// SwiftGet Firefox Addon - Background Script
// Intercepts downloads and forwards to native SwiftGet app

const NATIVE_APP_ID = "app.swiftget.downloader";

let nativePort = null;
let isConnected = false;
let pendingQueue = [];

// ── Native Messaging Connection ──────────────────────────────────────────────

function connectToNativeApp() {
  try {
    nativePort = browser.runtime.connectNative(NATIVE_APP_ID);

    nativePort.onMessage.addListener((msg) => {
      console.log("[SwiftGet] Native app message:", msg);
      handleNativeMessage(msg);
    });

    nativePort.onDisconnect.addListener(() => {
      console.warn("[SwiftGet] Native app disconnected:", browser.runtime.lastError?.message);
      isConnected = false;
      nativePort = null;
      // Retry connection after 5s
      setTimeout(connectToNativeApp, 5000);
    });

    isConnected = true;
    console.log("[SwiftGet] Connected to native app");

    // Flush pending queue
    pendingQueue.forEach(msg => sendToNative(msg));
    pendingQueue = [];

  } catch (err) {
    console.error("[SwiftGet] Failed to connect:", err);
    isConnected = false;
    setTimeout(connectToNativeApp, 5000);
  }
}

function sendToNative(message) {
  if (!isConnected || !nativePort) {
    pendingQueue.push(message);
    connectToNativeApp();
    return;
  }
  try {
    nativePort.postMessage(message);
  } catch (err) {
    console.error("[SwiftGet] Send failed:", err);
    pendingQueue.push(message);
    isConnected = false;
    connectToNativeApp();
  }
}

// ── Download Interception ────────────────────────────────────────────────────

// File extensions that should be intercepted
const INTERCEPT_EXTENSIONS = new Set([
  "zip", "rar", "7z", "tar", "gz", "bz2", "xz",
  "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v",
  "mp3", "flac", "wav", "aac", "ogg", "m4a",
  "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
  "dmg", "pkg", "iso", "exe", "msi",
  "jpg", "jpeg", "png", "gif", "webp", "svg",
  "apk", "ipa", "deb", "rpm",
  "torrent"
]);

// MIME types to always intercept
const INTERCEPT_MIME = new Set([
  "application/zip",
  "application/x-rar-compressed",
  "application/x-7z-compressed",
  "application/octet-stream",
  "application/x-msdownload",
  "video/",
  "audio/"
]);

function shouldIntercept(downloadItem) {
  const url = downloadItem.url || "";
  const mime = (downloadItem.mime || "").toLowerCase();
  const filename = downloadItem.filename || "";

  // Check file extension
  const ext = filename.split(".").pop()?.toLowerCase() ||
               url.split("?")[0].split(".").pop()?.toLowerCase() || "";
  if (INTERCEPT_EXTENSIONS.has(ext)) return true;

  // Check MIME type
  for (const m of INTERCEPT_MIME) {
    if (mime.startsWith(m)) return true;
  }

  return false;
}

browser.downloads.onCreated.addListener(async (downloadItem) => {
  if (!shouldIntercept(downloadItem)) return;

  console.log("[SwiftGet] Intercepting download:", downloadItem.url);

  // Cancel the browser download
  try {
    await browser.downloads.cancel(downloadItem.id);
    await browser.downloads.erase({ id: downloadItem.id });
  } catch (err) {
    console.warn("[SwiftGet] Could not cancel download:", err);
  }

  // Get referrer from active tab
  let referrer = "";
  try {
    const tabs = await browser.tabs.query({ active: true, currentWindow: true });
    referrer = tabs[0]?.url || "";
  } catch (_) {}

  // Get cookies for authenticated downloads
  let cookies = "";
  try {
    const cookieList = await browser.cookies.getAll({ url: downloadItem.url });
    cookies = cookieList.map(c => `${c.name}=${c.value}`).join("; ");
  } catch (_) {}

  // Forward to native app
  sendToNative({
    action: "download",
    url: downloadItem.url,
    filename: downloadItem.filename ? downloadItem.filename.split("/").pop() : "",
    referrer,
    cookies,
    mime: downloadItem.mime || "",
    fileSize: downloadItem.fileSize || -1,
    timestamp: Date.now()
  });

  // Show notification
  browser.notifications.create({
    type: "basic",
    iconUrl: "icons/icon48.png",
    title: "SwiftGet",
    message: `다운로드가 SwiftGet으로 전송되었습니다.`
  });
});

// ── Message Handlers ─────────────────────────────────────────────────────────

function handleNativeMessage(msg) {
  switch (msg.type) {
    case "status":
      // Native app reporting back download status
      break;
    case "error":
      browser.notifications.create({
        type: "basic",
        iconUrl: "icons/icon48.png",
        title: "SwiftGet 오류",
        message: msg.message || "알 수 없는 오류"
      });
      break;
    case "ping":
      sendToNative({ action: "pong" });
      break;
  }
}

// ── Popup Communication ───────────────────────────────────────────────────────

browser.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "getStatus") {
    sendResponse({ connected: isConnected });
    return true;
  }
  if (msg.action === "focusApp") {
    sendToNative({ action: "focus" });
    sendResponse({ ok: true });
    return true;
  }
  if (msg.action === "manualDownload") {
    sendToNative({
      action: "download",
      url: msg.url,
      filename: "",
      referrer: "",
      cookies: "",
      mime: "",
      fileSize: -1,
      timestamp: Date.now()
    });
    sendResponse({ ok: true });
    return true;
  }
});

// ── Init ─────────────────────────────────────────────────────────────────────

connectToNativeApp();
console.log("[SwiftGet] Addon loaded");
