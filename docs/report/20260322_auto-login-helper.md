# SF ログイン自動化で実現した構造的変更

## 1. Browser 操作の共通モジュール抽出 — Chrome 起動・WebDriver 接続の Single Access Point 化

### Before

```
session_keeper.py
├─ launch_chrome()          ← Chrome 起動ロジック直書き
├─ connect_driver()         ← WebDriver 接続ロジック直書き
└─ from selenium import ... ← try/except で guard

dl_batch.py
└─ subprocess.Popen(cmd)    ← WebDriver 接続なし（subprocess のみ）

問題: session_keeper と dl_batch で Chrome 操作の共通基盤がなかった
      dl_batch がログイン状態を確認する手段を持っていなかった
```

### After

```
browser.py ★ NEW
├─ launch_chrome()
├─ connect_driver()
├─ try_connect_driver()     ★ 接続失敗を None で返す
├─ wait_page_load()         ★ readyState 待機
└─ _import_selenium()       ★ lazy import（未インストール環境でも import 可）

session_keeper.py                    dl_batch.py
├─ from .browser import ...          ├─ from .browser import ...
└─ ✗ 削除: launch_chrome 直書き      └─ ★ NEW: WebDriver 接続で login check

効果: Chrome 操作の entry point が browser.py に集約
      selenium の lazy import で dl_batch のテストが壊れない
```

---

## 2. ログイン自動化モジュール — 手動 `input()` 待ちの廃止

### Before

```
session_keeper.py main() の流れ:

  Chrome 起動
      ▼
  input("ログインしたら Enter を押す...")   ← ★ 手動ブロッキング
      ▼
  connect_driver()
      ▼
  keep_alive ループ

問題: MFA 含め全て手動。自動化の余地がなかった
```

### After

```
login_helper.py ★ NEW
├─ is_login_page(driver)      URL + DOM (#username/#password) で判定
├─ is_mfa_page(driver)        URL に verify/identity を含むか
├─ is_logged_in(driver)       ↑ 2つの否定 + salesforce.com ドメイン確認
├─ fill_credentials(driver)   WebDriverWait → ID/PW 入力 → Login click
├─ wait_until_logged_in()     timeout なし polling（30秒ごとにログ）
├─ ensure_logged_in()         ★ 統合 entry point
└─ find_login_tab()           全タブ走査でログインページ検出

session_keeper.py main() の流れ:

  Chrome 起動
      ▼
  connect_driver()
      ▼
  driver.get(url) + wait_page_load()
      ▼
  ensure_logged_in()          ← ★ 自動入力 + MFA 待ち
      ├─ ログイン済み → skip
      ├─ ログインページ → fill_credentials → MFA 待ち
      └─ MFA ページ → polling 待ち（Ctrl+C で中断可）
      ▼
  keep_alive ループ

効果: input() が不要に。ID/PW 自動入力後は MFA だけ手動
```

---

## 3. dl_batch の standalone 起動 + 2 段階ログインリカバリ

### Before

```
dl_batch.py の前提:

  session_keeper が Chrome を起動済み（remote debugging port 9222）
      ▼
  try_connect_driver()
      ├─ 成功 → login check
      └─ 失敗 → "接続不可 — login check skip"  ← ★ 何もしない
                  ▼
              export 開始（ログインできてないかもしれない）

  export_one() の流れ:

  subprocess.Popen(Chrome + export URL)
      ▼
  wait_for_new_download(timeout=600s)
      ├─ 成功 → ExportResult(success=True)
      └─ タイムアウト → ExportResult(success=False)  ← ★ セッション切れでも
                                                         600秒待って失敗

問題: session_keeper なしでは login check が丸ごと skip
      ログイン画面にリダイレクトされた場合、600秒無駄に待って失敗
```

### After

```
dl_batch.py main() — 2 つの起動パターン:

  パターン A: session_keeper が動いている
    try_connect_driver()
        └─ 成功 → login check → export

  パターン B: standalone（session_keeper なし）  ★ NEW
    try_connect_driver()
        └─ 失敗 + user_data_dir あり
             ▼
           launch_chrome(専用プロファイル)  ← 自前で起動
             ▼
           connect_driver() → login check → export
             ▼
           finally: chrome_proc.terminate()  ← exception-safe cleanup

  ※ --my-chrome 時は user_data_dir=None → 起動しない（手動ログイン前提）

  export_one() 内部 — login recovery:

  _run_export()
      ├─ 成功 → return
      └─ 失敗 + driver あり
             ▼
         find_login_tab()        ← 全タブ走査
             ├─ 未検出 → そのまま失敗
             └─ 検出
                  ▼
              ensure_logged_in() ← 自動ログイン
                  ▼
              _run_export()      ← 1回だけリトライ（無限ループ防止）

効果: session_keeper なしでも自律動作。セッション切れ時も自動復帰
      try/finally で Chrome プロセスの orphan を防止
```

---

## 4. Credentials の 2 層フォールバック — API 用と UI 用の分離

### Before

```
.env
├─ SF_USERNAME        ← API 用
├─ SF_PASSWORD        ← API 用
└─ SF_SECURITY_TOKEN

config.py
└─ create_sf_client()  ← SF_USERNAME / SF_PASSWORD を直接使用

問題: UI ログインと API 認証で異なる credentials を使えなかった
```

### After

```
.env
├─ SF_USERNAME           ← API 用（既存）
├─ SF_PASSWORD           ← API 用（既存）
├─ SF_SECURITY_TOKEN     ← API 用（既存）
├─ SF_LOGIN_USERNAME     ★ NEW（UI 用、optional）
└─ SF_LOGIN_PASSWORD     ★ NEW（UI 用、optional）

config.py
├─ create_sf_client()           ← SF_USERNAME / SF_PASSWORD（変更なし）
└─ get_login_credentials() ★ NEW
       SF_LOGIN_USERNAME ──→ 設定あり → 使用
                          └→ 未設定 → SF_USERNAME にフォールバック

効果: UI / API で credentials を分離可能。未設定なら互換動作
```

---

## 5. inline test の外部化 — production code とテストの分離

### Before

```
dl_batch.py (1052 lines)
├─ production code (lines 1-548)
└─ inline tests   (lines 549-1052)  ← ★ 同一ファイルに混在

file_dispatch.py (527 lines)
├─ production code (lines 1-247)
└─ inline tests   (lines 248-527)  ← ★ 同一ファイルに混在

_make_job() factory が 2 ファイルに重複（encode default だけ異なる）

問題: production と test が混在。pytest collection 時に
      selenium 等の依存が import され、CI で壊れやすい
```

### After

```
dl_batch.py (548 lines)              ← production only
file_dispatch.py (247 lines)         ← production only

tests/
├─ __init__.py                       ★ NEW（package 化）
├─ helpers.py                        ★ NEW（共通 make_job factory）
├─ test_dl_batch.py                  ★ NEW（27 tests）
└─ test_file_dispatch.py             ★ NEW（23 tests）

効果: production / test の完全分離
      _make_job 重複を helpers.py の make_job() に集約
```

---

## Before / After 比較

```
                        Before                    After
─────────────────────── ───────────────────────── ─────────────────────────
Chrome 起動             session_keeper 直書き      browser.py に集約
WebDriver 接続          session_keeper のみ        browser.py 共通化
ログイン待ち             input() 手動              自動入力 + MFA polling
selenium import         top-level (crash or exit)  lazy import
dl_batch 単独起動       login check skip           自前で Chrome 起動 + login
dl_batch ログイン       なし（600秒 timeout）      pre-flight check + recovery
Chrome cleanup          なし                      try/finally で確実に終了
リトライ                なし                      1回限り自動リトライ
Credentials             API 用のみ                UI 用 / API 用 分離
テスト配置               inline（同一ファイル）       tests/ に分離
_make_job factory       2箇所に重複                helpers.py に集約
新規 CLI options        —                         --port, --no-login-check
```

```
新規ファイル:   browser.py (70 lines), login_helper.py (130 lines)
               tests/__init__.py, tests/helpers.py (21 lines)
               tests/test_dl_batch.py (511 lines), tests/test_file_dispatch.py (290 lines)
変更ファイル:   config.py (+14), dl_batch.py (+164 -571), file_dispatch.py (-280)
               session_keeper.py (+70 -67), README.md (+79 -18)
テスト:        77 tests 全 pass
```

**まとめ:** session_keeper の `input()` 手動待ちを廃止し、`login_helper.py` による ID/PW 自動入力 + MFA 無限待ち polling に置き換えた。`browser.py` で Chrome 操作を共通化したことで、dl_batch にも pre-flight login check と timeout 時の login recovery（タブ走査 → 1回リトライ）を追加できた。さらに dl_batch が自前で Chrome を起動する path を追加し、session_keeper なしでも standalone で自律動作できるようにした（`try/finally` で Chrome プロセスの orphan を防止）。inline test は `tests/` に分離し、重複していた `_make_job` factory を `helpers.py` に集約。selenium は lazy import にして既存テスト 77 件が壊れないようにしつつ、credentials は UI/API 分離可能な 2 層フォールバック構成にした。README には 2 つの起動パターンと auto-login の仕組みを明文化した。
