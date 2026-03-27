# Chrome 起動遅延 (~60秒) の原因と修正

## 症状

`download_all.bat` をダブルクリックしてから Chrome が起動するまで約60秒かかる。
`keep_session.bat` は即座に Chrome が起動する。

session_keeper 経由ではなく download 単体で起動した場合に発生。
既にログイン済み (cookie が残っている) の場合でも、ログイン画面すら表示されずにダウンロードが始まるまで60秒待たされる。

## 原因

`download.py` は `prepare_salesforce_session(try_existing=True)` を呼ぶ。
この `try_existing=True` が問題の根本。

### try_existing=True の動作

```
prepare_salesforce_session(try_existing=True)
    │
    ▼
try_connect_driver(port=9222)
    │
    ▼
connect_driver(port=9222)
    │
    ▼
webdriver.Chrome(options=opts)   ← debuggerAddress: "127.0.0.1:9222"
    │
    ▼
TCP connect to 127.0.0.1:9222   ← 誰も listen していない
    │                                → TCP timeout ~60秒 ★
    ▼
WebDriverException → return None
    │
    ▼
launch_chrome()                  ← やっと Chrome 起動
```

`try_connect_driver` は「既に起動中の Chrome があれば接続する」ためのもの。
session_keeper が動いていれば port 9222 で Chrome が listen しているので即接続できる。
しかし session_keeper なしの場合、port 9222 は閉じている。
Selenium の `webdriver.Chrome()` は TCP 接続を試み、応答がないと OS レベルの TCP timeout (~60秒) まで待ってしまう。

### session_keeper が速い理由

session_keeper は `try_existing=False` (default) で呼ぶため、`try_connect_driver` を完全に skip して即 `launch_chrome` に進む。

```
session_keeper: try_existing=False → skip try_connect → launch_chrome (即座)
download:       try_existing=True  → try_connect → TCP timeout 60秒 → launch_chrome
```

## 修正

`browser.py` の `try_connect_driver` に socket による fast port check を追加。

```python
def is_port_open(port: int, timeout: float = 1.0) -> bool:
    """port が listen 中か socket で高速チェック。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False


def try_connect_driver(port=REMOTE_DEBUGGING_PORT):
    if not is_port_open(port):          # ← 追加: ~1秒で判定
        logger.debug("port %d は閉じている — 接続 skip", port)
        return None
    # 以下、従来の Selenium 接続
    ...
```

### Before / After

| 状態 | Before | After |
|---|---|---|
| Chrome 未起動 | ~60秒 (TCP timeout) | ~1秒 (socket check) |
| 普段使い Chrome のみ起動 (debug port なし) | ~60秒 (TCP timeout) | ~1秒 (socket check) |
| session_keeper 起動中 (port 9222 open) | 即接続 | 即接続 (変化なし) |

## 同時に修正した関連問題: Ctrl+C のエラー

Ctrl+C を押すと WebDriver が先に切断され、スクリプトの cleanup 処理でエラーが連鎖していた。

- `download.py`: `except KeyboardInterrupt` を追加 → traceback なしで終了
- `close_browser_session`: `except BaseException` で cleanup 中の全例外を握りつぶし → 1回の Ctrl+C で確実に終了

## 該当 commit

`9d98e69` — Add fast port check and clean Ctrl-C shutdown
