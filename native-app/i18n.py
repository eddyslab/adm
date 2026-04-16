# -*- coding: utf-8 -*-
"""
SwiftGet i18n — 다국어 지원
지원 언어: 한국어(ko), 영어(en), 일본어(ja), 중국어(zh), 불어(fr), 스페인어(es)
"""

LANGUAGES = {
    "ko": "한국어",
    "en": "English",
    "ja": "日本語",
    "zh": "中文",
    "fr": "Français",
    "es": "Español",
}

STRINGS = {
    # ──────────────────────────────────────────────────────────────
    "ko": {
        # 탭
        "tab_general":    "일반",
        "tab_download":   "다운로드",
        "tab_notify":     "알림",
        "tab_queue":      "대기 중",
        "tab_misc":       "기타",

        # 툴바 버튼
        "btn_clear_done": "완료 항목 지우기",
        "btn_folder":     "폴더 열기",
        "btn_import":     "URL 임포트",
        "btn_add_url":    "＋ URL 추가",
        "btn_download":   "다운로드",

        # URL 입력
        "url_hint":       "URL을 여기에 붙여넣기...",

        # 통계
        "stats_idle":     "대기 중...",
        "stats_fmt":      "전체 {total}개  ·  실행 중 {running}개  ·  완료 {done}개  ·  세그먼트 {seg}개",
        "stats_speed":    "  ·  ↓ {speed}",

        # 다운로드 목록
        "empty_list":     "다운로드 항목이 없습니다",

        # 다운로드 설정
        "lbl_save_dir":   "다운로드 경로:",
        "btn_browse":     "찾아보기…",
        "lbl_segments":   "기본 세그먼트 수:",
        "lbl_seg_hint":   "(1 = 분할 안 함)",

        # 알림 설정
        "lbl_notify":     "다운로드 완료 알림:",
        "chk_notify":     "완료 시 알림 표시",

        # 대기 중 탭
        "chk_auto_dedup": "중복 자동 제거",
        "btn_q_delete":   "삭제",
        "btn_q_dedup":    "중복 제거",
        "btn_q_run":      "실행",
        "queue_count":    "전체 {n}개",
        "queue_empty":    "임포트된 URL이 없습니다",
        "dedup_result":   "{n}개의 중복 항목이 제거됐습니다.",
        "dedup_title":    "중복 제거",

        # 기타 탭
        "lbl_language":   "언어:",
        "lbl_lang_hint":  "언어 변경 후 앱을 재시작해 주세요.",
        "btn_restart":    "재시작",

        # JobCard 상태
        "status_queued":    "대기",
        "status_running":   "다운로드 중",
        "status_paused":    "일시정지",
        "status_done":      "완료",
        "status_error":     "오류",
        "status_cancelled": "취소됨",

        # JobCard 정보
        "info_error":     "오류: {msg}",
        "info_eta":       "남은 시간 {eta}",

        # 알림 메시지
        "notif_done":     "다운로드 완료: {fname}",

        # 다이얼로그
        "dlg_add_url_title":  "URL 추가",
        "dlg_add_url_prompt": "다운로드 URL:",
        "dlg_import_title":   "URL 목록 파일 선택",
        "dlg_import_filter":  "텍스트 파일 (*.txt)|*.txt|모든 파일 (*.*)|*.*",
        "dlg_import_done":    "{n}개의 URL이 추가됐습니다.",
        "dlg_import_done_title": "임포트 완료",
        "dlg_dir_title":      "다운로드 경로 선택",

        # 메뉴바
        "menu_open":      "SwiftGet 열기",
        "menu_folder":    "다운로드 폴더",
        "menu_quit":      "종료",
    },

    # ──────────────────────────────────────────────────────────────
    "en": {
        "tab_general":    "General",
        "tab_download":   "Download",
        "tab_notify":     "Notifications",
        "tab_queue":      "Queue",
        "tab_misc":       "Misc",

        "btn_clear_done": "Clear Completed",
        "btn_folder":     "Open Folder",
        "btn_import":     "Import URLs",
        "btn_add_url":    "＋ Add URL",
        "btn_download":   "Download",

        "url_hint":       "Paste URL here...",

        "stats_idle":     "Idle...",
        "stats_fmt":      "Total {total}  ·  Running {running}  ·  Done {done}  ·  Segments {seg}",
        "stats_speed":    "  ·  ↓ {speed}",

        "empty_list":     "No downloads",

        "lbl_save_dir":   "Download Path:",
        "btn_browse":     "Browse…",
        "lbl_segments":   "Default Segments:",
        "lbl_seg_hint":   "(1 = no splitting)",

        "lbl_notify":     "Download Notifications:",
        "chk_notify":     "Notify on completion",

        "chk_auto_dedup": "Auto remove duplicates",
        "btn_q_delete":   "Delete",
        "btn_q_dedup":    "Remove Duplicates",
        "btn_q_run":      "Start",
        "queue_count":    "Total {n}",
        "queue_empty":    "No imported URLs",
        "dedup_result":   "{n} duplicate(s) removed.",
        "dedup_title":    "Remove Duplicates",

        "lbl_language":   "Language:",
        "lbl_lang_hint":  "Please restart the app after changing the language.",
        "btn_restart":    "Restart",

        "status_queued":    "Queued",
        "status_running":   "Downloading",
        "status_paused":    "Paused",
        "status_done":      "Done",
        "status_error":     "Error",
        "status_cancelled": "Cancelled",

        "info_error":     "Error: {msg}",
        "info_eta":       "ETA {eta}",

        "notif_done":     "Download complete: {fname}",

        "dlg_add_url_title":  "Add URL",
        "dlg_add_url_prompt": "Download URL:",
        "dlg_import_title":   "Select URL List File",
        "dlg_import_filter":  "Text files (*.txt)|*.txt|All files (*.*)|*.*",
        "dlg_import_done":    "{n} URL(s) added.",
        "dlg_import_done_title": "Import Complete",
        "dlg_dir_title":      "Select Download Path",

        "menu_open":      "Open SwiftGet",
        "menu_folder":    "Downloads Folder",
        "menu_quit":      "Quit",
    },

    # ──────────────────────────────────────────────────────────────
    "ja": {
        "tab_general":    "一般",
        "tab_download":   "ダウンロード",
        "tab_notify":     "通知",
        "tab_queue":      "待機中",
        "tab_misc":       "その他",

        "btn_clear_done": "完了項目を消去",
        "btn_folder":     "フォルダを開く",
        "btn_import":     "URLインポート",
        "btn_add_url":    "＋ URL追加",
        "btn_download":   "ダウンロード",

        "url_hint":       "URLをここに貼り付け...",

        "stats_idle":     "待機中...",
        "stats_fmt":      "合計 {total}  ·  実行中 {running}  ·  完了 {done}  ·  セグメント {seg}",
        "stats_speed":    "  ·  ↓ {speed}",

        "empty_list":     "ダウンロード項目はありません",

        "lbl_save_dir":   "保存先:",
        "btn_browse":     "参照…",
        "lbl_segments":   "デフォルトセグメント数:",
        "lbl_seg_hint":   "(1 = 分割なし)",

        "lbl_notify":     "ダウンロード完了通知:",
        "chk_notify":     "完了時に通知",

        "chk_auto_dedup": "重複を自動削除",
        "btn_q_delete":   "削除",
        "btn_q_dedup":    "重複削除",
        "btn_q_run":      "実行",
        "queue_count":    "合計 {n}件",
        "queue_empty":    "インポートされたURLはありません",
        "dedup_result":   "{n}件の重複項目が削除されました。",
        "dedup_title":    "重複削除",

        "lbl_language":   "言語:",
        "lbl_lang_hint":  "言語変更後、アプリを再起動してください。",
        "btn_restart":    "再起動",

        "status_queued":    "待機",
        "status_running":   "ダウンロード中",
        "status_paused":    "一時停止",
        "status_done":      "完了",
        "status_error":     "エラー",
        "status_cancelled": "キャンセル",

        "info_error":     "エラー: {msg}",
        "info_eta":       "残り時間 {eta}",

        "notif_done":     "ダウンロード完了: {fname}",

        "dlg_add_url_title":  "URLを追加",
        "dlg_add_url_prompt": "ダウンロードURL:",
        "dlg_import_title":   "URLリストファイルを選択",
        "dlg_import_filter":  "テキストファイル (*.txt)|*.txt|すべてのファイル (*.*)|*.*",
        "dlg_import_done":    "{n}件のURLが追加されました。",
        "dlg_import_done_title": "インポート完了",
        "dlg_dir_title":      "保存先を選択",

        "menu_open":      "SwiftGetを開く",
        "menu_folder":    "ダウンロードフォルダ",
        "menu_quit":      "終了",
    },

    # ──────────────────────────────────────────────────────────────
    "zh": {
        "tab_general":    "常规",
        "tab_download":   "下载",
        "tab_notify":     "通知",
        "tab_queue":      "队列",
        "tab_misc":       "其他",

        "btn_clear_done": "清除已完成",
        "btn_folder":     "打开文件夹",
        "btn_import":     "导入URL",
        "btn_add_url":    "＋ 添加URL",
        "btn_download":   "下载",

        "url_hint":       "在此粘贴URL...",

        "stats_idle":     "空闲中...",
        "stats_fmt":      "共 {total}  ·  运行中 {running}  ·  已完成 {done}  ·  分段 {seg}",
        "stats_speed":    "  ·  ↓ {speed}",

        "empty_list":     "没有下载项目",

        "lbl_save_dir":   "下载路径:",
        "btn_browse":     "浏览…",
        "lbl_segments":   "默认分段数:",
        "lbl_seg_hint":   "(1 = 不分段)",

        "lbl_notify":     "下载完成通知:",
        "chk_notify":     "完成时通知",

        "chk_auto_dedup": "自动删除重复",
        "btn_q_delete":   "删除",
        "btn_q_dedup":    "删除重复",
        "btn_q_run":      "开始",
        "queue_count":    "共 {n} 项",
        "queue_empty":    "没有导入的URL",
        "dedup_result":   "已删除 {n} 个重复项。",
        "dedup_title":    "删除重复",

        "lbl_language":   "语言:",
        "lbl_lang_hint":  "更改语言后请重启应用。",
        "btn_restart":    "重启",

        "status_queued":    "等待中",
        "status_running":   "下载中",
        "status_paused":    "已暂停",
        "status_done":      "已完成",
        "status_error":     "错误",
        "status_cancelled": "已取消",

        "info_error":     "错误: {msg}",
        "info_eta":       "剩余时间 {eta}",

        "notif_done":     "下载完成: {fname}",

        "dlg_add_url_title":  "添加URL",
        "dlg_add_url_prompt": "下载URL:",
        "dlg_import_title":   "选择URL列表文件",
        "dlg_import_filter":  "文本文件 (*.txt)|*.txt|所有文件 (*.*)|*.*",
        "dlg_import_done":    "已添加 {n} 个URL。",
        "dlg_import_done_title": "导入完成",
        "dlg_dir_title":      "选择下载路径",

        "menu_open":      "打开SwiftGet",
        "menu_folder":    "下载文件夹",
        "menu_quit":      "退出",
    },

    # ──────────────────────────────────────────────────────────────
    "fr": {
        "tab_general":    "Général",
        "tab_download":   "Téléchargement",
        "tab_notify":     "Notifications",
        "tab_queue":      "File d'attente",
        "tab_misc":       "Divers",

        "btn_clear_done": "Effacer terminés",
        "btn_folder":     "Ouvrir dossier",
        "btn_import":     "Importer URLs",
        "btn_add_url":    "＋ Ajouter URL",
        "btn_download":   "Télécharger",

        "url_hint":       "Coller l'URL ici...",

        "stats_idle":     "En attente...",
        "stats_fmt":      "Total {total}  ·  En cours {running}  ·  Terminé {done}  ·  Segments {seg}",
        "stats_speed":    "  ·  ↓ {speed}",

        "empty_list":     "Aucun téléchargement",

        "lbl_save_dir":   "Dossier de téléchargement:",
        "btn_browse":     "Parcourir…",
        "lbl_segments":   "Segments par défaut:",
        "lbl_seg_hint":   "(1 = pas de découpage)",

        "lbl_notify":     "Notification de fin:",
        "chk_notify":     "Notifier à la fin",

        "chk_auto_dedup": "Supprimer les doublons auto",
        "btn_q_delete":   "Supprimer",
        "btn_q_dedup":    "Supprimer doublons",
        "btn_q_run":      "Démarrer",
        "queue_count":    "Total {n}",
        "queue_empty":    "Aucune URL importée",
        "dedup_result":   "{n} doublon(s) supprimé(s).",
        "dedup_title":    "Supprimer doublons",

        "lbl_language":   "Langue:",
        "lbl_lang_hint":  "Veuillez redémarrer l'app après avoir changé la langue.",
        "btn_restart":    "Redémarrer",

        "status_queued":    "En attente",
        "status_running":   "Téléchargement",
        "status_paused":    "Pausé",
        "status_done":      "Terminé",
        "status_error":     "Erreur",
        "status_cancelled": "Annulé",

        "info_error":     "Erreur: {msg}",
        "info_eta":       "Temps restant {eta}",

        "notif_done":     "Téléchargement terminé: {fname}",

        "dlg_add_url_title":  "Ajouter URL",
        "dlg_add_url_prompt": "URL de téléchargement:",
        "dlg_import_title":   "Sélectionner fichier de liste URL",
        "dlg_import_filter":  "Fichiers texte (*.txt)|*.txt|Tous les fichiers (*.*)|*.*",
        "dlg_import_done":    "{n} URL(s) ajoutée(s).",
        "dlg_import_done_title": "Import terminé",
        "dlg_dir_title":      "Sélectionner le dossier de téléchargement",

        "menu_open":      "Ouvrir SwiftGet",
        "menu_folder":    "Dossier Téléchargements",
        "menu_quit":      "Quitter",
    },

    # ──────────────────────────────────────────────────────────────
    "es": {
        "tab_general":    "General",
        "tab_download":   "Descarga",
        "tab_notify":     "Notificaciones",
        "tab_queue":      "Cola",
        "tab_misc":       "Otros",

        "btn_clear_done": "Limpiar completados",
        "btn_folder":     "Abrir carpeta",
        "btn_import":     "Importar URLs",
        "btn_add_url":    "＋ Añadir URL",
        "btn_download":   "Descargar",

        "url_hint":       "Pegar URL aquí...",

        "stats_idle":     "En espera...",
        "stats_fmt":      "Total {total}  ·  En curso {running}  ·  Completado {done}  ·  Segmentos {seg}",
        "stats_speed":    "  ·  ↓ {speed}",

        "empty_list":     "No hay descargas",

        "lbl_save_dir":   "Ruta de descarga:",
        "btn_browse":     "Examinar…",
        "lbl_segments":   "Segmentos predeterminados:",
        "lbl_seg_hint":   "(1 = sin división)",

        "lbl_notify":     "Notificación de descarga:",
        "chk_notify":     "Notificar al completar",

        "chk_auto_dedup": "Eliminar duplicados auto",
        "btn_q_delete":   "Eliminar",
        "btn_q_dedup":    "Eliminar duplicados",
        "btn_q_run":      "Iniciar",
        "queue_count":    "Total {n}",
        "queue_empty":    "No hay URLs importadas",
        "dedup_result":   "{n} duplicado(s) eliminado(s).",
        "dedup_title":    "Eliminar duplicados",

        "lbl_language":   "Idioma:",
        "lbl_lang_hint":  "Reinicie la app después de cambiar el idioma.",
        "btn_restart":    "Reiniciar",

        "status_queued":    "En espera",
        "status_running":   "Descargando",
        "status_paused":    "Pausado",
        "status_done":      "Completado",
        "status_error":     "Error",
        "status_cancelled": "Cancelado",

        "info_error":     "Error: {msg}",
        "info_eta":       "Tiempo restante {eta}",

        "notif_done":     "Descarga completa: {fname}",

        "dlg_add_url_title":  "Añadir URL",
        "dlg_add_url_prompt": "URL de descarga:",
        "dlg_import_title":   "Seleccionar archivo de lista URL",
        "dlg_import_filter":  "Archivos de texto (*.txt)|*.txt|Todos los archivos (*.*)|*.*",
        "dlg_import_done":    "{n} URL(s) añadida(s).",
        "dlg_import_done_title": "Importación completa",
        "dlg_dir_title":      "Seleccionar ruta de descarga",

        "menu_open":      "Abrir SwiftGet",
        "menu_folder":    "Carpeta de descargas",
        "menu_quit":      "Salir",
    },
}


def get_strings(lang: str) -> dict:
    """언어 코드에 해당하는 문자열 딕셔너리 반환. 없으면 영어로 폴백."""
    return STRINGS.get(lang, STRINGS["en"])