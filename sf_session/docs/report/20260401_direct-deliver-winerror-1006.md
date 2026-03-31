# direct-deliver で WinError 1006 (ERROR_FILE_INVALID)

## 症状

`03_download_direct.bat`（`--direct-deliver` モード）でダウンロード実行中に
WinError 1006 が発生し、ファイルの移動に失敗する。

移動先フォルダは存在しており、事前の probe check（touch + unlink）は通っている。

## WinError 1006 とは

Win32 エラーコード 1006 = `ERROR_FILE_INVALID`。

> "The volume for a file has been externally altered so that the opened file is no longer valid."

ファイル操作中に対象ボリュームのハンドルが無効化された、という OS レベルのエラー。
ネットワークドライブ（SMB / mapped drive）で接続が一時的に途切れた場合に発生しやすい。

## 原因

`runner.py` の `export_batch` 内で `shutil.move()` を呼ぶ箇所（235行目付近）。

### direct-deliver の処理フロー

```
1. probe_destinations()          ← 全移動先フォルダを touch+unlink で事前 check → OK
2. for each job:
     Chrome で export URL を開く
     download_dir (ローカル) にファイルが落ちる
     build_destination()         ← output_dir=None → Path(job.src_folder_name) を使用
     shutil.move(local, network) ← ★ ここで WinError 1006
```

### なぜ probe は通るのに move で失敗するか

- probe（手順1）から実際の move（手順2）まで数分〜数十分の時間差がある
- その間にネットワーク接続が不安定になると、ファイルハンドルが stale 化する
- `shutil.move` は cross-device（local → network）の場合、内部で `shutil.copy2` → `os.unlink` にフォールバックする
- `copy2` の途中でネットワークボリュームの handle が無効になり 1006 が発生

### 通常モード（non-direct-deliver）で起きにくい理由

通常モードでは `output_dir` がローカルの work_dir になるため、
`shutil.move` はローカル → ローカルのコピーになる。
ネットワーク越しのコピーは後段の swap/deliver で別途行われる。

## 対処方針

`runner.py` の `export_batch` 内の `shutil.move` 呼び出しに retry を追加する。

ネットワーク一時断は短時間で復帰することが多いため、
数秒の wait を挟んだ 2〜3 回の retry で大半のケースに対応できる。
