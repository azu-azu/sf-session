"""excel関連の共通ユーティリティ。"""

def col_to_index(col_letter: str) -> int:
    """Excel 列文字を 1-based インデックスに変換する。"""
    result = 0
    for ch in col_letter.upper():
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result


def get_cell_value(ws, row: int, col_letter: str):
    """ワークシートからセル値を取得する。"""
    return ws.cell(row=row, column=col_to_index(col_letter)).value