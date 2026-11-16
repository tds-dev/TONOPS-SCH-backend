<!-- 週間勤務・稼働停止予定の拠点への直接関連付け、開発用DBの作成手順と確認観点を説明する資料。 -->

# 2026-11-16 カレンダーの拠点への直接関連付け

`M_Locations.CalendarID`を削除し、週間勤務・稼働停止予定を`LocationID`で直接取得する。
停止予定の`CalendarID`は`LocationID`へ置き換える。勤務行の`CalendarID`は勤務1件の主キーとして残す。

## 変更前後

| 対象 | 変更前 | 変更後 |
| --- | --- | --- |
| M_Locations | 代表勤務行のCalendarIDを保持 | 代表勤務行を保持しない |
| M_Calendars | LocationIDで拠点に所属 | 変更なし |
| M_CalendarExceptions | CalendarIDから勤務行を経由して拠点を参照 | LocationIDで拠点を直接参照 |
| 稼働時間API | GET /api/v1/calendars/{calendarId}/working-time | GET /api/v1/locations/{locationId}/working-time |
| 勤務削除 | 拠点・停止予定の参照先を付け替える | 勤務行だけを論理削除 |

停止予定の一覧・新規登録・部分更新は`locationId`を使い、保存項目に旧`calendarId`を含めない。
週間勤務の登録・編集・削除では、拠点や停止予定の更新履歴を書き換えない。
停止予定は共通CRUDの`locationId`検索を使い、勤務行を結合する専用検索を削除する。
共通の数値検索は、不正な数値を入力エラー（HTTP 422）として返す。

## 維持する動作

- 同じ曜日の午前・午後など複数勤務、昼休み、日曜0～土曜6、日本時間の日時を維持する。
- 停止予定は拠点内の全設備に適用し、別拠点の勤務・停止予定は混ぜない。
- 有効な勤務行が未登録の場合だけ常時稼働とする。登録済み勤務の休日や全面停止は稼働なしとする。
- 停止予定が残る場合、最後の勤務行の削除を拒否する。勤務未登録時の停止予定登録も拒否する。
- 同じ拠点への勤務変更・停止予定保存はSQL Serverで直列化し、上記条件を保護する。
- 計画計算では稼働枠を一度だけ展開し、設備間で共有する。
- 画面の入力欄、週間表示、週切替、再表示、未保存確認などの既存操作を維持する。

## 開発用DBの再作成

開発用DBの構成を変更した場合は、DBを削除して現在の定義で再作成する。
今回の作業はソースコード・作成クエリ・仮データ挿入クエリの更新までで、実DBの削除・再作成は行わない。

DBを削除した後、SSMSで次の順にクエリを実行する。

1. `DataBase/query/create_database_sqlserver.sql`：DBを作成する。
2. `DataBase/query/schema_sqlserver.sql`：今回の関連付けを含むテーブル・制約を作成する。
3. `DataBase/query/seed_demo_sqlserver.sql`：パン工場、週間勤務12件、製品・オーダー・下書き計画などを登録する。

Pythonの`DataBase.setup_database`を使う場合も、現在のモデル定義と仮データで作成する。
同処理は既存テーブルの列を変更しないため、旧DBを残したままの構造更新には使用しない。
作成後はフロントエンドとバックエンドを同じ変更版で起動する。

## 確認する操作

1. 同じ拠点に月曜午前・午後、火曜勤務を登録し、昼休みと休日が稼働に含まれないこと。
2. 稼働停止予定を登録・編集・削除し、画面と計画計算の両方に反映されること。
3. 勤務行を削除しても停止予定が保持され、停止予定の監査情報が変わらないこと。
4. 停止予定が残る最後の勤務行は削除できず、停止予定削除後に全勤務を削除すると常時稼働になること。
5. 拠点を切り替えた際に、他拠点の勤務・停止予定が混ざらないこと。

SQL Serverの再作成と実画面の操作確認は別途必要。ビルド・外部通信は実施しない。

## 変更ファイル

バックエンド：

| ファイル | 変更内容 |
| --- | --- |
| `app/models/masters.py` | 拠点のCalendarIDを削除し、停止予定をLocationIDへ変更。代表行専用の制約も削除 |
| `app/services/calendar_service.py` | LocationIDから勤務・停止予定を取得。代表行の選択・付け替え・専用検索を削除 |
| `app/engine/snapshot.py` | 計画の稼働枠をLocationIDから取得し、設備間で共有 |
| `app/routers/masters.py` | 稼働時間APIを拠点単位へ変更。不要になった確認・検索処理を削除 |
| `app/routers/crud.py` | 数値検索の変換失敗をHTTP 422として返す |
| `app/services/demo_seed.py` | 仮データから代表勤務行の設定を削除 |
| `DataBase/query/schema_sqlserver.sql` | 新規作成用の列・外部キー・一意制約を更新 |
| `DataBase/query/seed_demo_sqlserver.sql` | 拠点のCalendarID挿入と代表行UPDATEを削除 |
| `DataBase/setup_database.py` | 現行の関連付けとDB再作成前提の説明を追記 |
| `README.md` | 現行仕様とDB再作成手順への案内を更新 |
| `docs/SYSTEM_OVERVIEW.md` | テーブル定義・ER図・画面対応・API説明を更新 |
| `docs/DB_SCHEMA_UPDATE_20261111.md` | 過去の代表行方式と現在の方式を区別する案内を追記 |
| `docs/CALENDAR_LOCATION_LINK_20261116.md` | 今回の仕様・維持する動作・作成手順・確認結果を記録 |

フロントエンド：

| ファイル | 変更内容 |
| --- | --- |
| `src/app/interfaces/master.interface.ts` | 拠点の型からcalendarIdを削除 |
| `src/app/services/master-catalog.service.ts` | 代表行選択を、選択中の拠点に勤務があるかの判定へ変更 |
| `src/app/services/api.service.ts` | 稼働時間の取得先をlocationsのAPIへ変更 |
| `src/app/components/main/calendars/calendars.component.ts` | 停止予定の検索・保存・稼働時間取得をLocationIDへ統一 |
| `README.md` | 現行仕様とDB再作成前提の説明を追記 |

## 確認結果

- 昼休み・休日・停止時間、別拠点の分離、勤務削除後の停止予定・監査情報保持を確認。
- 作成SQLの変更対象3テーブルについて列・関連付けと仮データSQLを照合。
- SQL Server上での作成クエリ実行とブラウザ操作は未実施。
- ビルド・コード解析コマンド・Git操作・実DBの削除や再作成は未実施。
