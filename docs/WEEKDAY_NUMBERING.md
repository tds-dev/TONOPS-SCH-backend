<!-- 日曜0～土曜6の曜日番号、変更理由・対象ファイル・確認結果を記録する資料。 -->
# 曜日番号の統一

> 現行仕様の追記（2026-11-11）：夜勤を廃止し、週次勤務は同日内のEndTime > StartTimeだけを受け付ける。以下の夜勤に関する記載は廃止前の変更記録。

DayOfWeekおよび画面で共用する許可曜日の番号を次へ統一した。

| 値 | 曜日 |
|---|---|
| 0 | 日 |
| 1 | 月 |
| 2 | 火 |
| 3 | 水 |
| 4 | 木 |
| 5 | 金 |
| 6 | 土 |

## 変更前と変更後

以前は日曜が7で、DB制約・API入力確認・画面が1～7を使っていた。
変更後は日曜を0とし、0～6を受理する。月曜1～土曜6は同じ番号を維持する。

Pythonが返す曜日番号は画面・DBの番号と異なるため、`weekday_number`に変換を共通化した。
勤務時間の展開と許可曜日ルールの両方でこの関数を使い、判定の食い違いを防ぐ。
画面の共通選択肢は日・月・火・水・木・金・土の順となる。
許可曜日ルールの入力範囲・日曜の表示名も同じ番号へ揃える。

## 仮データと既存機能

仮データは月～土06:00～12:00、13:00～18:00の12行を維持する。
月～土は引き続き1～6なので、SQLとPythonの登録値は変わらない。日曜は休みのため0の勤務行を追加しない。
平日だけ製造するルールの[1,2,3,4,5]も維持する。
日時の日本時間保存、停止例外、昼休み・夜勤、製品・オーダー・計画の構成は変更しない。

既存DBの曜日7は、この変更だけでは0へ自動変換しない。今回もDB再作成を前提とし、バックエンドで`python -m DataBase.setup_database`を実行して新定義を作成する。
実DBへの接続・変更は行っていない。

## 確認結果と画面確認

- Python構文確認とメモリDBの32件のテストが成功。
- 日曜0・土曜6のAPI登録、勤務展開、-1・7・8の拒否を確認。
- 1週間すべての曜日番号と、日曜限定ルールの禁止区間・表示名を確認。
- 仮データ12行、昼休み・日曜休みの維持を確認。
- SQLの制約・仮データ、画面の選択肢、Excelの説明とXML構造を確認。
- 検証用Pythonにpydantic-settingsがないため、DB・APIの検証時は設定取得だけを固定値へ差し替えた。

画面では、日曜を選んで保存するとDayOfWeek=0になること、日曜のみの勤務が月曜に混ざらないこと、許可曜日の「日」が正しく表示されることを確認する。

## 変更ファイル

- `backend/app/models/masters.py`
- `backend/app/services/calendar_service.py`
- `backend/app/services/worktime.py`
- `backend/app/engine/rules/allowed_weekdays.py`
- `backend/DataBase/query/schema_sqlserver.sql`
- `backend/DataBase/query/seed_demo_sqlserver.sql`
- `backend/app/services/demo_seed.py`
- `backend/docs/SYSTEM_OVERVIEW.md`
- `backend/tests/test_order_crud.py`
- `backend/app/core/timeutil.py`
- `frontend/src/app/services/master-form.ts`
- `frontend/src/app/components/main/rules/rules.component.ts`
- `frontend/docs/Book1.xlsx`
- `backend/docs/WEEKDAY_NUMBERING.md`（この変更記録）
