## バッチファイル一覧 (root)

| # | ファイル                                          | 機能                                              |
|---|--------------------------------------------------|---------------------------------------------------|
| 1 | ■00_keep_session.bat                             | セッション維持 (Chrome 起動 + ログイン + 定期 reload) |
| 2 | 01_stay_awake.bat                                | Windows スリープ防止 (--minutes で時間指定、0 で無制限) |
| 3 | 97_clean_cache.bat                               | キャッシュファイルのクリーンアップ                     |
| 4 | 98_setup_初回または設定更新の場合のみ実行する.bat      | 初回セットアップ (venv + 依存 install)               |
| 5 | 99_new_pipeline.bat                              | 新規 pipeline 作成                                 |

各 pipeline の bat については pipelines/<name>/readme.txt を参照。

---

## 初回セットアップ

1. ローカルにこのフォルダを置く
2. `98_setup_初回または設定更新の場合のみ実行する.bat` をダブルクリック
3. `.env` を開き、環境に合わせて設定値を記入する

---

## 新規 pipeline の追加手順

pipeline = 「ダウンロード → 振り分け → 変換」をまとめた単位。

1. 99_new_pipeline.bat をダブルクリックし、pipeline 名を入力
2. MACRO_ROOT_PATH/<name>/ に マクロファイル（xlsmファイル） を配置
3. 動作確認:
   - pipelines\<name>\90_show_macrofile.bat   … ジョブ定義の確認

---

## 追加休業日 (extra_holidays.csv)

pipelines/extra_holidays.csv に YYYY-MM-DD を1行ずつ書くと、営業日チェックで休業日扱いになる。
ファイルが無ければ無視される（既存動作に影響なし）。

  例:
    2026-12-31
    2027-01-02
    2027-01-03

---

## 補足）ターミナルから実行する場合

### 初回

必ずこのフォルダの場所でターミナルを起動する。

```
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r sf_session\requirements.txt
```

### 2回目以降

```
.\.venv\Scripts\Activate.ps1
py -m sf_session.keeper
```

※ログインしたら自動検知して keep-alive 開始。Ctrl+C で停止。

### venv に入らずに実行する場合

```
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r sf_session\requirements.txt
.\.venv\Scripts\python.exe -m sf_session.keeper
```
