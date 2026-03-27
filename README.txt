## バッチファイル一覧 (root)

| # | ファイル                                          | 機能                                              |
|---|--------------------------------------------------|---------------------------------------------------|
| 1 | ■00_keep_session.bat                             | セッション維持 (Chrome 起動 + ログイン + 定期 reload) |
| 2 | 97_clean_cache.bat                               | キャッシュファイルのクリーンアップ                     |
| 3 | 98_setup_初回または設定更新の場合のみ実行する.bat    | 初回セットアップ (venv + 依存 install)               |
| 4 | 99_new_pipeline.bat                              | 新規 pipeline 作成                                 |

各 pipeline の bat については pipelines/<name>/readme.txt を参照。

---

## 初回セットアップ

1. ローカルにこのフォルダを置く
2. `98_setup_初回または設定更新の場合のみ実行する.bat` をダブルクリック
3. `.env` を開き、環境に合わせて設定値を記入する

---

==============================
 新規 pipeline の追加手順
==============================

pipeline = 「ダウンロード → 振り分け → 変換」をまとめた単位。
部署やチームごとに pipeline を分けて運用する。


----------------------------------------------------------------------
 Step 1: 99_new_pipeline.bat をダブルクリック
----------------------------------------------------------------------

  pipeline名を入力してください: monthly

  ※ 名前は英数字・ハイフン・アンダースコアのみ（日本語・スペース不可）
  ※ 事前に 98_setup〜.bat を実行済みであること

  → 以下が自動で作られる:

    pipelines/monthly/
      ├── ★01_download.bat    … 全件 export
      ├── ★02_振り分け.bat     … Box フォルダへ振り分け
      ├── 11〜90_*.bat        … その他のバッチ
      ├── readme.txt          … bat の使い方ガイド
      ├── result/
      └── ids_file/

    OUTPUT_ROOT_PATH/monthly/csv/            … csv 出力先
    MACRO_ROOT_PATH/monthly/             … マクロファイル格納先

    .env の PIPELINES に "monthly" が追記される


----------------------------------------------------------------------
 Step 2: マクロファイル（.xlsm）を配置する
----------------------------------------------------------------------

  自動作成された MACRO_ROOT_PATH/monthly/ に xlsm を格納する。
  既存 pipeline の xlsm をコピーして編集するのが早い。

  xlsm の SalseForce シート（101 行目〜）にレポート定義を記入:

    AA列 … No
    AB列 … export URL（末尾の report ID を抽出）
    AC列 … リネーム後ファイル名（空なら元名維持）
    AD列 … 移動先フォルダパス
    AE列 … エンコーディング（空なら Shift_JIS）
    AG列 … skip フラグ（値があればスキップ）


----------------------------------------------------------------------
 Step 3: 動作確認
----------------------------------------------------------------------

  1) ジョブ定義が正しく読めるか確認:

     pipelines\monthly\90_show_macrofile.bat

  2) dry-run で export 対象を確認（実行はしない）:

     pipelines\monthly\★01_download.bat --dry-run


----------------------------------------------------------------------
 Step 4（任意）: ids.txt で対象を絞る
----------------------------------------------------------------------

  全件ではなく特定レポートだけ処理したい場合:

  pipelines/monthly/ids_file/ids.txt を作成し、
  1行1つ report ID を書く（# で始まる行はコメント）

    # 対象レポート
    00O000000000001AAA
    00O000000000002AAA


----------------------------------------------------------------------
 実行例
----------------------------------------------------------------------

  > 99_new_pipeline.bat

  pipeline名を入力してください: monthly

  ✓ .env の PIPELINES を更新しました: archive, monthly
  ✓ pipelines/monthly/ を作成しました
    - result/
    - ids_file/
  ✓ bat ファイルを配置しました (7 files)
  ✓ readme.txt を配置しました
  ✓ Z:\Users\you\macros\monthly を作成しました
  ⚠ マクロファイル (.xlsm) を Z:\Users\you\macros\monthly に格納してください
  ✓ Z:\Users\you\outputs\monthly\csv を作成しました

  セットアップ完了！

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
