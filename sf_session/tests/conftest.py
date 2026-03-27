"""テスト共通設定。config.py の module-level 定数が import 時に必要とする環境変数を設定。"""
import os

# config.py が import 時に os.environ[] で参照する必須変数。
# .env がないテスト環境でも import が通るようにデフォルト値を設定する。
_TEST_DEFAULTS = {
    "SF_BASE_URL": "https://test.salesforce.com",
    "PIPELINES": '{"archive": "."}',
}

for key, value in _TEST_DEFAULTS.items():
    os.environ.setdefault(key, value)
