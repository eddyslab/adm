# SwiftGet — macOS 다운로드 매니저

Firefox에서 링크를 우클릭하면 **SwiftGet 앱**으로 다운로드를 전달하는 네이티브 다운로드 매니저입니다.

---

## 아키텍처

```
사용자가 링크 우클릭 → "SwiftGet으로 다운로드"
              │
              ▼
Firefox 브라우저
              │  Native Messaging (stdin/stdout)
              ▼
SwiftGet 애드온 (background.js)
   - URL, Referer, Cookie 수집
   - 파일명 자동 감지 (쿼리 파라미터 → HEAD → Content-Type)
              │  Unix Socket
              ▼
swiftget-host.py  (Native Messaging 브리지)
              │
              ▼
SwiftGet.app  (wxPython GUI 다운로드 매니저)
   - 최대 N 세그먼트 병렬 다운로드 (설정 가능)
   - 세그먼트별 진행 상태 표시
   - 일시정지 / 재개 / 취소
   - 메뉴바 상주 + Dock 표시
   - 다운로드 경로 및 세그먼트 수 설정
```

---

## 프로젝트 구조

```
adm/
├── addon/                          # Firefox 애드온
│   ├── manifest.json               # 권한 선언 (contextMenus, cookies 등)
│   ├── background.js               # 우클릭 메뉴 등록 및 다운로드 전달
│   ├── popup.html                  # 툴바 팝업 UI
│   └── popup.js                    # 팝업 로직
│
├── native-app/                     # macOS 네이티브 앱
│   ├── swiftget.py                 # GUI 다운로드 매니저 (wxPython)
│   ├── swiftget-host.py            # Native Messaging 브리지
│   ├── setup.py                    # py2app 빌드 설정
│   ├── icons/
│   │   └── SwiftGet.icns           # 앱 아이콘
│   └── app.swiftget.downloader.json  # 개발용 매니페스트
│
├── installer/
│   └── install.sh                  # DMG 빌더 (개발자용)
│
└── dist/
    └── SwiftGet.dmg                # 배포용 DMG (빌드 후 생성)
```

---

## 설치 방법 (사용자)

1. `SwiftGet.dmg`를 열어 `SwiftGet.app`을 응용 프로그램 폴더로 드래그
2. `SwiftGet.app`을 한 번 실행 (Native Messaging 매니페스트 자동 등록)
3. Firefox에서 `about:addons` → 톱니바퀴 → 파일에서 부가 기능 설치 → `SwiftGet.xpi` 선택

> 보안 경고가 뜨면: 시스템 설정 → 개인정보 보호 및 보안 → 허용

---

## 빌드 방법 (개발자)

### 요구사항
- macOS 12 이상
- Python 3.9 이상
- Firefox 91 이상

### 사전 준비

```bash
pip3 install wxPython py2app
```

`native-app/icons/SwiftGet.icns` 파일이 있어야 합니다.

### DMG 빌드

```bash
bash installer/install.sh
```

빌드 스크립트가 자동으로 다음을 수행합니다:
1. `SwiftGet.app` 빌드 (`py2app`)
2. 아이콘 번들에 적용
3. Native Messaging 호스트 스크립트 포함
4. Firefox 애드온 `.xpi` 패키징
5. `dist/SwiftGet.dmg` 생성

### 개발 모드 직접 실행

```bash
pip3 install wxPython
python3 native-app/swiftget.py
```

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 우클릭 다운로드 | 링크·이미지·동영상 우클릭 → "SwiftGet으로 다운로드" |
| 다중 세그먼트 | 파일을 N개 구간으로 나눠 병렬 다운로드 (서버 지원 시) |
| 세그먼트 시각화 | 전체 진행바 아래 세그먼트별 진행 상태 표시 |
| 일시정지/재개 | 다운로드 중 언제든 일시정지 가능 |
| 파일명 자동 감지 | 쿼리 파라미터 → HEAD 요청 → Content-Type 순서로 감지 |
| 인증 지원 | Cookie, Referer 헤더 자동 전달 |
| 설정 저장 | 다운로드 경로, 세그먼트 수 설정 (config.json 영속화) |
| 메뉴바 상주 | 메뉴바에서 실시간 다운로드 속도 표시 |

---

## 설정 파일 위치

```
~/Library/Application Support/SwiftGet/config.json   # 사용자 설정
~/Library/Application Support/SwiftGet/swiftget.sock # Unix 소켓
~/Library/Logs/SwiftGet/swiftget.log                 # 앱 로그
~/Library/Logs/SwiftGet/host.log                     # 호스트 로그
```

---

## 라이선스

MIT License