// SwiftGet Firefox Addon - Background Script
// 우클릭 컨텍스트 메뉴로 SwiftGet에 다운로드 전송

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
      setTimeout(connectToNativeApp, 5000);
    });

    isConnected = true;
    console.log("[SwiftGet] Connected to native app");

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

// ── 파일명 감지 ───────────────────────────────────────────────────────────────

async function resolveFilename(url) {
  let filename = "";

  // 1. pathname 마지막 세그먼트
  try {
    const u = new URL(url);
    filename = decodeURIComponent(u.pathname.split("/").pop() || "");

    // 2. 확장자 없으면 쿼리 파라미터에서 힌트 추출 (fm=jpg, format=png 등)
    if (filename && !filename.includes(".")) {
      const fmt = u.searchParams.get("fm")
               || u.searchParams.get("format")
               || u.searchParams.get("ext")
               || u.searchParams.get("type");
      if (fmt) filename = `${filename}.${fmt.toLowerCase()}`;
    }
  } catch (_) {}

  // 3. 여전히 확장자 없으면 HEAD 요청으로 헤더 확인
  if (filename && !filename.includes(".")) {
    try {
      const res = await fetch(url, { method: "HEAD", credentials: "include" });

      // Content-Disposition: attachment; filename="foo.jpg"
      const cd = res.headers.get("content-disposition") || "";
      const cdMatch = cd.match(/filename[*]?=(?:UTF-8'')?["']?([^"';\r\n]+)/i);
      if (cdMatch) {
        filename = decodeURIComponent(cdMatch[1].trim());
      } else {
        // Content-Type → 확장자 매핑
        const ct = (res.headers.get("content-type") || "").split(";")[0].trim();
        const EXT_MAP = {
          "image/jpeg":        "jpg",
          "image/png":         "png",
          "image/gif":         "gif",
          "image/webp":        "webp",
          "image/svg+xml":     "svg",
          "image/avif":        "avif",
          "video/mp4":         "mp4",
          "video/webm":        "webm",
          "video/quicktime":   "mov",
          "audio/mpeg":        "mp3",
          "audio/ogg":         "ogg",
          "audio/flac":        "flac",
          "application/zip":   "zip",
          "application/pdf":   "pdf",
        };
        const ext = EXT_MAP[ct];
        if (ext) filename = `${filename}.${ext}`;
      }
    } catch (_) {}
  }

  return filename;
}

// ── Context Menu ─────────────────────────────────────────────────────────────

browser.contextMenus.create({
  id: "swiftget-download-link",
  title: "SwiftGet으로 다운로드",
  contexts: ["link"],
});

browser.contextMenus.create({
  id: "swiftget-download-media",
  title: "SwiftGet으로 다운로드",
  contexts: ["image", "video", "audio"],
});

browser.contextMenus.onClicked.addListener(async (info, tab) => {
  const url = info.linkUrl || info.srcUrl || info.pageUrl;
  if (!url) return;

  console.log("[SwiftGet] Context menu download:", url);

  const referrer = tab?.url || "";

  let cookies = "";
  try {
    const cookieList = await browser.cookies.getAll({ url });
    cookies = cookieList.map(c => `${c.name}=${c.value}`).join("; ");
  } catch (_) {}

  const filename = await resolveFilename(url);

  sendToNative({
    action: "download",
    url,
    filename,
    referrer,
    cookies,
    mime: "",
    fileSize: -1,
    timestamp: Date.now()
  });

  browser.notifications.create({
    type: "basic",
    iconUrl: "icons/icon48.png",
    title: "SwiftGet",
    message: `${filename || url} 다운로드가 전송되었습니다.`
  });
});

// ── Message Handlers ─────────────────────────────────────────────────────────

function handleNativeMessage(msg) {
  switch (msg.type) {
    case "status":
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
    (async () => {
      let cookies = "";
      try {
        const cookieList = await browser.cookies.getAll({ url: msg.url });
        cookies = cookieList.map(c => `${c.name}=${c.value}`).join("; ");
      } catch (_) {}

      let referrer = "";
      try {
        const tabs = await browser.tabs.query({ active: true, currentWindow: true });
        referrer = tabs[0]?.url || "";
      } catch (_) {}

      const filename = await resolveFilename(msg.url);

      sendToNative({
        action: "download",
        url: msg.url,
        filename,
        referrer,
        cookies,
        mime: "",
        fileSize: -1,
        timestamp: Date.now()
      });
    })();
    sendResponse({ ok: true });
    return true;
  }
});

// ── Init ─────────────────────────────────────────────────────────────────────

connectToNativeApp();
console.log("[SwiftGet] Addon loaded");