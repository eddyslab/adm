# SwiftGet — Firefox 다운로드 매니저

파이어폭스 브라우저의 다운로드를 가로채서 별도 실행 중인 **SwiftGet 앱**으로 전달하는
네이티브 다운로드 매니저입니다.

---

## 아키텍처

```
웹 페이지 (다운로드 클릭)
       │
       ▼
Firefox 브라우저
       │  downloads.onCreated 이벤트
       ▼
SwiftGet 애드온 (background.js)
   - 브라우저 다운로드 즉시 취소
   - URL, Referer, Cookie 수집
       │  Native Messaging (stdin/stdout)
       ▼
swiftget-host  (Python 브리지)
       │  Unix Socket
       ▼
SwiftGet.app  (GUI 다운로드 매니저)
   - 최대 8세그먼트 병렬 다운로드
   - 일시정지 / 재개 / 취소
   - 메뉴바 상주 (Dock 미표시)
   - 다운로드 목록 UI
```

---

## 프로젝트 구조

```
firefox-dm/
├── addon/                     # 파이어폭스 애드온
│   ├── manifest.json          # 애드온 매니페스트 (Native Messaging 권한)
│   ├── background.js          # 다운로드 이벤트 감지 & 전달
│   ├── popup.html             # 툴바 팝업 UI
│   └── popup.js               # 팝업 로직
│
├── native-app/                # macOS 네이티브 앱
│   ├── swiftget.py            # GUI 다운로드 매니저 (메인)
│   ├── swiftget-host.py       # Native Messaging 브리지
│   ├── setup.py               # py2app 빌드 설정
│   └── app.swiftget.downloader.json  # 개발용 매니페스트
│
└── installer/
    └── install.sh             # macOS 자동 설치 스크립트
```

---

## 설치 방법

### 요구사항
- macOS 12 이상
- Python 3.9 이상
- Firefox 91 이상

### 자동 설치

```bash
git clone <repo>
cd firefox-dm
bash installer/install.sh
```

설치 스크립트가 자동으로 다음을 수행합니다:
1. Python 패키지 설치 (`rumps`, `py2app`)
2. `SwiftGet.app` 빌드 및 `/Applications` 에 복사
3. Firefox Native Messaging 매니페스트 등록
4. 파이어폭스 애드온 `.xpi` 패키징

### 수동 설치 (개발자용)

**1. Python 패키지 설치**
```bash
pip3 install rumps py2app
```

**2. .app 빌드**
```bash
cd native-app
python3 setup.py py2app
cp -R dist/SwiftGet.app /Applications/
```

**3. Native Messaging 매니페스트 등록**
```bash
mkdir -p ~/Library/Application\ Support/Mozilla/NativeMessagingHosts
cp native-app/app.swiftget.downloader.json \
   ~/Library/Application\ Support/Mozilla/NativeMessagingHosts/
```
`path` 값을 실제 `swiftget-host` 실행 파일 경로로 수정하세요.

**4. Firefox 애드온 설치**
- `about:addons` 열기
- 톱니바퀴 아이콘 → "파일에서 부가 기능 설치"
- `swiftget.xpi` 선택

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 자동 감지 | zip, mp4, mp3, pdf 등 30+ 확장자 자동 차단 |
| 다중 세그먼트 | 파일 1개를 최대 8조각으로 나눠 병렬 다운로드 |
| 일시정지/재개 | 다운로드 중 언제든 일시정지 가능 |
| 메뉴바 상주 | Dock에 미표시, 메뉴바에서 속도 실시간 표시 |
| URL 직접 추가 | 팝업 또는 앱에서 URL 직접 입력 |
| 인증 지원 | Cookie, Referer 헤더 자동 전달 |

---

## 인터셉트 대상 확장자

```
압축:   zip, rar, 7z, tar, gz, bz2, xz
영상:   mp4, mkv, avi, mov, wmv, flv, webm, m4v
음악:   mp3, flac, wav, aac, ogg, m4a
문서:   pdf, doc, docx, xls, xlsx, ppt, pptx
앱:     dmg, pkg, iso, exe, msi, apk, ipa, deb, rpm
이미지: jpg, jpeg, png, gif, webp, svg
기타:   torrent
```

---

## 개발 / 디버깅

**로그 파일 위치:**
```
~/Library/Logs/SwiftGet/host.log    # Native host 로그
~/Library/Logs/SwiftGet/swiftget.log # GUI 앱 로그
```

**소켓 경로:**
```
~/Library/Application Support/SwiftGet/swiftget.sock
```

**개발 모드로 앱 직접 실행:**
```bash
pip3 install rumps
python3 native-app/swiftget.py
```

---

## 라이선스

MIT License
