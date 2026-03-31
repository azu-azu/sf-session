# Chrome 未起動時に chromedriver が見つからずエラーになる

## 症状

`download` を Chrome 未起動の状態で実行すると "chrome driver のパスが見つからない" エラーで落ちる。
先に `keep_session`（keeper）を立ち上げておくと download は正常に動作する。

## 原因

### connect_driver() の chromedriver 依存

`browser.py:connect_driver()` は `webdriver.Chrome(options=opts)` を呼ぶ。
`debuggerAddress` で既存 Chrome に接続する場合でも、Selenium は **chromedriver プロセス** をローカルで起動する（protocol bridge として必要）。

```python
# browser.py
def connect_driver(port: int = REMOTE_DEBUGGING_PORT) -> WebDriver:
    webdriver, Options, _, _ = _import_selenium()
    opts = Options()
    opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    driver = webdriver.Chrome(options=opts)  # ← Service 未指定 = Selenium Manager 任せ
    return driver
```

`Service(executable_path=...)` を渡していないため、chromedriver の発見は **Selenium Manager に丸投げ**。
Selenium Manager が chromedriver を見つけられない（PATH にない、cache にない、download できない）と例外で死ぬ。

### keeper 経由だと動く理由

keeper が起動済みなら port 9222 が open → download は `try_connect_driver()` 経由で既存 Chrome に接続する。

```
【Chrome 未起動 → download 単体実行】

try_connect_driver(9222)
  → is_port_open(9222) → False         ← port 閉じてるので即 None（Selenium 未呼出し）
  → return None

driver is None
  → launch_chrome()                     ← Chrome を subprocess.Popen で起動
  → time.sleep(5)
  → connect_driver(9222)               ← ★ 初めて Selenium Manager が走る
    → webdriver.Chrome(options=opts)
    → chromedriver を探す → 見つからない → ERROR
```

```
【keeper 起動済み → download 実行】

try_connect_driver(9222)
  → is_port_open(9222) → True          ← keeper の Chrome が listen 中
  → connect_driver(9222)
    → webdriver.Chrome(options=opts)
    → chromedriver は keeper 起動時に cache 済み → 成功
  → return driver

driver is not None
  → launch_chrome() をスキップ           ← Chrome 起動不要
```

核心: **keeper を先に起動すると、その時点で Selenium Manager が chromedriver を cache に入れる**。
以後の download からの `connect_driver()` は cache hit で成功する。

keeper なしで download を初回起動すると、Selenium Manager が chromedriver を resolve できずに落ちる。

### 考えられる直接原因（要エラーログで確認）

| # | 原因 | 確認方法 |
|---|------|---------|
| 1 | Chrome 自動更新で version が上がり、cache 済み chromedriver と version mismatch | `chrome --version` と cache 内の chromedriver version を比較 |
| 2 | Selenium Manager のネットワークアクセスが blocked（proxy / firewall） | Selenium Manager を手動実行して network error を確認 |
| 3 | chromedriver が PATH にも cache にも存在しない | `where chromedriver` / Selenium cache dir を確認 |

## 実装案

### 案 A: connect_driver に retry + wait を追加（最小変更）

Chrome 起動直後の `connect_driver()` 失敗が一時的なものである可能性もある。
retry を入れて、Selenium Manager や Chrome debug port の準備完了を待つ。

```python
# browser.py

def connect_driver(
    port: int = REMOTE_DEBUGGING_PORT,
    *,
    retries: int = 0,
    retry_wait: float = 3.0,
) -> WebDriver:
    """起動済み Chrome に Selenium で接続。"""
    webdriver, Options, WebDriverException, _ = _import_selenium()
    opts = Options()
    opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")

    last_err: Exception | None = None
    for attempt in range(1 + retries):
        try:
            driver = webdriver.Chrome(options=opts)
            logger.info("WebDriver 接続完了")
            return driver
        except WebDriverException as e:
            last_err = e
            if attempt < retries:
                logger.debug(
                    "WebDriver 接続失敗 (attempt %d/%d): %s — %.0fs 後にリトライ",
                    attempt + 1, 1 + retries, e, retry_wait,
                )
                time.sleep(retry_wait)
    raise last_err  # type: ignore[misc]
```

`prepare_salesforce_session()` の Chrome 起動後の呼び出しだけ retry 付きにする:

```python
# session.py（変更箇所のみ）

driver = connect_driver(port=port, retries=2, retry_wait=3.0)
```

**Pros:** 変更が小さい。Selenium Manager の cache warm-up も retry 間に完了しうる。
**Cons:** chromedriver が本当に存在しない場合は retry しても無駄。

### 案 B: Selenium Manager の事前チェック + chromedriver path 明示（根本修正）

chromedriver の resolve を Selenium Manager 任せにせず、明示的に管理する。

```python
# browser.py

from selenium.webdriver.chrome.service import Service

def _resolve_chromedriver() -> str:
    """Selenium Manager で chromedriver path を解決し、存在を事前確認。"""
    from selenium.webdriver.common.selenium_manager import SeleniumManager

    try:
        result = SeleniumManager().binary_paths(["--browser", "chrome"])
        driver_path = result["driver_path"]
    except Exception as e:
        raise RuntimeError(
            "chromedriver を自動取得できません。"
            "ネットワーク接続を確認するか、chromedriver を PATH に配置してください。"
        ) from e

    if not Path(driver_path).is_file():
        raise FileNotFoundError(f"chromedriver が見つかりません: {driver_path}")

    return driver_path


def connect_driver(port: int = REMOTE_DEBUGGING_PORT) -> WebDriver:
    """起動済み Chrome に Selenium で接続。"""
    webdriver, Options, _, _ = _import_selenium()
    chromedriver_path = _resolve_chromedriver()

    opts = Options()
    opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=opts)
    logger.info("WebDriver 接続完了 (chromedriver=%s)", chromedriver_path)
    return driver
```

**Pros:** エラーメッセージが明確。chromedriver の有無を Selenium 接続前に検証できる。
**Cons:** Selenium Manager の内部 API (`binary_paths`) に依存するため、Selenium version upgrade で壊れるリスクがある。

### 案 C: webdriver-manager で chromedriver を管理（外部依存追加）

```bash
pip install webdriver-manager
```

```python
# browser.py

from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def connect_driver(port: int = REMOTE_DEBUGGING_PORT) -> WebDriver:
    webdriver, Options, _, _ = _import_selenium()
    opts = Options()
    opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    logger.info("WebDriver 接続完了")
    return driver
```

**Pros:** Chrome version に追従して chromedriver を自動 download・cache。実績のある library。
**Cons:** 外部依存が 1 つ増える。ネットワーク blocked な環境では結局同じ問題。

### 推奨

**案 A（retry）を先に入れて様子を見る**。
多くのケースで Chrome 起動の timing issue + Selenium Manager の cache miss が原因なので、retry で吸収できる可能性が高い。

それでも再発するなら案 B or C で chromedriver 管理を明示化する。
案 C は dependency 増だが最も robust。proxy 環境なら `WDM_SSL_VERIFY=0` 等の設定も可能。

## 未確定事項

- 実際のエラーメッセージ（traceback）の確認 → 直接原因の特定に必要
- Selenium Manager の cache dir（`%LOCALAPPDATA%\selenium\manager`）の状態確認
- Chrome の自動更新履歴の確認
