## バッチファイル一覧

| # | ファイル                | 機能                                    |
|---|------------------------|-----------------------------------------|
| 1 | ★01_download.bat      | 全件 export (営業日のみ実行)              |
| 2 | ★02_振り分け.bat       | Box フォルダへ振り分け                    |
| 3 | 11_download_ids.bat    | ids.txt 指定 export                     |
| 4 | 12_download_retry.bat  | 失敗分リトライ                           |
| 5 | 20_jis_to_utf.bat      | UTF-8 BOM 変換                          |
| 6 | 21_file_collect.bat    | CSV 収集                                |
| 7 | 90_show_macrofile.bat  | ジョブ定義表示                           |

ダブルクリックで実行。PowerShell に D&D すれば引数追加も可能。
バッチファイルの名前は自由に変えても問題ない。

---

## ターミナルから実行する場合

venv を activate した状態で実行する。

```
#### 全件 export (outputs/<pipeline>/csv/ に集約)
py -m sf_session.download

#### ids.txt でフィルタして export
py -m sf_session.download --ids-file

#### 失敗分だけリトライ
py -m sf_session.download --retry

#### Box フォルダへ振り分け
py -m sf_session.file_deliver

#### UTF-8 BOM 変換
py -m sf_session.jis_to_utf8

#### CSV 収集
py -m sf_session.file_collect

#### ジョブ定義を確認
py -m sf_session.macro_book_reader

#### dry-run でジョブ一覧を確認
py -m sf_session.download --dry-run
```

---

## download の主なオプション

```
--force             営業日チェックを skip して強制実行
--direct-deliver    Box フォルダに per-job 振り分け (default: outputs/<pipeline>/csv/ に集約)
--ids-file          ids.txt の report ID でフィルタ
--retry             前回の success_ids を読み、失敗分だけ再実行
--date-suffix       ファイル名に _YYYYMMDD を付与
--no-login-check    起動時の login check を skip
--interval          レポート間 wait 秒 (default: 2.0)
--timeout           per-report タイムアウト秒 (default: 600)
--open-download-dir Download フォルダを Explorer で開く
--open-output-dir   出力先フォルダを Explorer で開く
--dry-run           実行せずジョブ一覧を表示
```
