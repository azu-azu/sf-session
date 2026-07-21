# direct-deliver をタスクスケジューラ登録すると翌日以降が動かない

## 症状

`03_download_direct.bat`（`--direct-deliver` モード）を Windows タスクスケジューラに
登録して毎営業日実行している。

月曜が祝日だった日、コンソールには

```
非営業日のため skip (japanese_holiday: ...)
```

と表示されたが、そこから先に進まず **止まったまま** になった。
想定では「月曜は skip、火曜はまた動く」だが、**火曜になっても動かなかった**。

## 原因：バッチ末尾の `pause`

skip 自体は正常動作。`sf_session.download` は非営業日に

```python
logger.info("非営業日のため skip (%s)", reason)
return 0
```

と **exit code 0 で正常終了** している（`cli.py` の営業日判定ブロック）。

問題は Python 終了後、バッチが末尾の `pause` に到達すること。

```bat
.venv\Scripts\python.exe -m sf_session.download {pipeline} --direct-deliver %*
pause    ← ここでキー入力待ちのまま停止
```

`pause` は「続行するには何かキーを押してください...」でキー入力を待つ命令。
手動ダブルクリック実行ではコンソールを閉じずに結果を確認できる利点があるが、
**タスクスケジューラの無人実行ではキーが押されることは永遠にない**。

その結果、バッチを実行している `cmd.exe` が終了せず生き残る。

### なぜ火曜が動かないのか

タスクスケジューラから見ると、この `cmd.exe` が生きている限り
**タスクは「実行中」のまま** である。

タスクスケジューラの「設定」タブにある
**「既にタスクが実行中の場合の規則」の既定値は「新しいインスタンスを開始しない」**。

つまり月曜のインスタンスが `pause` で居座ったまま火曜のトリガが来ると、
「まだ前回が実行中」と判断され、火曜のトリガは黙って無視される。
これが「skip されて止まっていると翌日反応してくれない」の正体。

> 補足: これは skip 特有ではない。通常の営業日でも DL 完了後に `pause` へ到達するため、
> 本来は毎回ハングしていたはず。祝日 skip は Python が即 return するので、
> `pause` で止まっている状態が「非営業日のため skip」直後に露骨に見えただけ。

## 求める挙動

- **通常実行（成功/失敗）** … コンソールを残したい。成功か失敗かをログで確認するため。
  → `pause` は必要。
- **非営業日 skip** … コンソールを残さず即終了したい。
  → `pause` してはいけない（残ると翌営業日のトリガをブロックする）。

つまり「skip のときだけ pause しない」を区別する必要がある。

> 当初は `pause` を環境変数 `SF_NO_PAUSE` でガードする案だったが、これだと
> `SF_NO_PAUSE=1` を立てた瞬間に**通常実行でも pause しなくなり**、
> 「結果ログを見たい」用途が潰れる。skip と通常実行を区別できないため不十分だった。

## 対処

### 1. skip 専用の exit code で区別する（本コミットの修正）

Python 側は skip も成功も `return 0` で、exit code だけでは区別できなかった。
そこで **非営業日 skip 時だけ専用 exit code（`SKIP_EXIT_CODE = 42`）を返す**ようにし、
bat 側でその code のときだけ pause を飛ばす。

`business_day.py`:

```python
SKIP_EXIT_CODE = 42
```

`download/cli.py`（営業日判定ブロック）:

```python
if not should_run:
    logger.info("非営業日のため skip (%s)", reason)
    return SKIP_EXIT_CODE
```

`_BAT_TEMPLATE`:

```bat
.venv\Scripts\python.exe -m {module} {pipeline}{extra_args} %*
if %errorlevel% equ 42 exit /b 0     rem 非営業日 skip → pause せず即終了
if not defined SF_NO_PAUSE pause     rem 通常実行（成功/失敗）→ pause してログを残す
```

これで挙動は下表のとおり。**タスクスケジューラ側の環境変数設定は不要**。

| ケース | exit code | pause | コンソール |
| ------ | --------- | ----- | ---------- |
| 通常実行 成功 | 0  | する   | 残る（ログ確認）→ 手動で閉じる |
| 通常実行 失敗 | 1  | する   | 残る（エラー確認）→ 手動で閉じる |
| 非営業日 skip | 42 | しない | 残らない → 翌営業日のトリガをブロックしない |

`SF_NO_PAUSE=1` は「完全無人で pause を一切させたくない」場合の任意の上書きとして残してある。

既存 pipeline の bat には `--regen-bats`（または `setup.bat`）で反映する。

### 2. タスクスケジューラ側（防御的・推奨）

「設定」タブで **「タスクを停止するまでの時間」を有効化**（例: 1 時間）しておくと、
`pause` に限らず実際のダウンロードが Chrome 側でハングした場合にも自動終了し、
次回トリガをブロックしない。

## まとめ

| 層 | 問題 | 対処 |
|----|------|------|
| バッチ | skip と通常実行を区別せず pause して無人実行でハング | skip 専用 exit code (42) のときだけ pause を飛ばす |
| スケジューラ | 実行中扱いで翌日トリガが無視される | 実行時間のタイムアウトを有効化 |
