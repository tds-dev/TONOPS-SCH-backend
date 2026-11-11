<!-- 2026-11-11の組織削除・週次カレンダー統合、新規DB作成手順と確認観点を説明する資料。 -->

> 最新の日時仕様：DBは日本時間の`datetime2(7)`、通常APIは日本時間（`+09:00`）で入出力。ボードは描画用に時差表記なしの日本時間を使用する。DBは再作成して使用する。過去のUTCに関する記録は変更当時の仕様。詳細はバックエンドの`docs/DATETIME_JST.md`を参照。
# DB構成変更（2026-11-11）

削除済みのDBを新しく作成するため、作成SQL・仮データSQL・Pythonモデル・API・画面・フロントエンドの`docs/Book1.xlsx`を同じ定義へ揃える。全27テーブル・313カラム。

## 組織と関連列の削除

`M_Organizations`を削除し、`M_Locations.OrganizationID`と`M_AttributeDefinitions.OrganizationID`も削除する。属性定義の重複防止は`EntityType`＋`AttributeKey`へ変更する。

Python初期設定のデモ登録済み判定は、組織名から拠点名「パン工場」へ変更する。手動SQLの空DB確認も組織テーブルに依存しない形へ変更する。

## 拠点ごとの週次カレンダー

1拠点に1つの週次カレンダーを持たせ、曜日・時間帯は`M_Calendars`の複数行で登録する。DB上の行の関係は、拠点1行に対して勤務行が複数行となる。

例として、月曜午前・月曜午後・火曜午前などを別々の勤務行で保存する。デモは月〜土の06:00–12:00と13:00–18:00の12行を登録し、日曜は勤務を登録しない。

`M_Locations.DefaultCalendarID`を`CalendarID`へ改名し、週次カレンダーを代表する勤務行のIDを保存する。勤務時間の計算では、その1行だけでなく同じ`LocationID`の有効な勤務行全体を使う。設備の`CalendarID`による関連付けも同じ拠点の週次カレンダーへ接続する。

最初の勤務登録時に代表行を自動設定する。勤務行を削除するときは、拠点・設備・停止例外の参照を残る勤務行へまとめて移す。最後の勤務行は停止例外が残る間は削除せず、停止例外がなければ参照を解除し、従来の「カレンダーなし＝常時稼働」へ戻す。同じ拠点の同時変更はSQL Serverの行ロックで順番に処理し、削除済みの勤務行へ参照が残ることを防ぐ。

| M_Calendarsの列 | 型・意味 |
|---|---|
| CalendarID | INT、主キー、自動採番。曜日・時間帯1件を識別 |
| LocationID | INT、必須。所属拠点を参照 |
| DayOfWeek | SMALLINT、必須。1＝月曜〜7＝日曜 |
| StartTime | TIME、必須。日本時間の開始時刻 |
| EndTime | TIME、必須。同日内で開始時刻より後の終了時刻 |
| WorkName | NVARCHAR(50)、NULL可。午前・午後などの勤務名 |
| CreatedAt | DATETIME2、必須。登録日時をUTCで保存 |
| CreatedBy | NVARCHAR(254)、NULL可。登録者 |
| UpdatedAt | DATETIME2、NULL可。最終更新日時をUTCで保存 |
| UpdatedBy | NVARCHAR(254)、NULL可。最終更新者 |
| DeleteFlag | BIT、必須。0＝通常、1＝削除済み |

`M_CalendarPatterns`を削除し、`DayOfWeek`・`StartTime`・`EndTime`をカレンダー本体へ移す。勤務名は`ShiftName`から`WorkName`へ改名する。

`CalendarName`・`ParentCalendarID`は削除する。親カレンダーからの継承と、旧勤務行の`ValidFrom`・`ValidTo`による適用期間の設定も廃止する。監査列は他テーブルと共通の`UpdatedAt`・`UpdatedBy`を継続する。

## 例外を休日・設備停止へ統一

`M_CalendarExceptions.StartAt`を`StartTime`、`EndAt`を`EndTime`へ改名する。この2列の型はDATETIME2のままで、日付を含むUTC日時を保存する。曜日勤務のTIME型と区別する。

`IsWorking`を削除し、登録した例外をすべて休日・設備停止として稼働枠から除外する。残業・休日出勤の追加機能は廃止する。`CalendarID`は拠点の代表勤務行を参照し、`Reason`と履歴列は維持する。

## 名称と既存機能への影響

製品切替は既存の`M_ProductSwitchTimes`・`ProductSwitchTimeID`・`ProductSwitchTimeName`を維持する。IDは1件を表す単数形とし、`M_ProductSwitchRules`の関連列も`ProductSwitchTimeID`に揃える。

変更対象は組織・カレンダーと、その参照・初期設定・画面表示。製品→工程→実行候補、オーダーとタスク、段取り替え、計画の作成・複製・比較・手動割付・承認の定義は維持する。勤務枠を取得する部分を新構成へ接続し、午前午後の間の休憩、日曜休み、休日・停止の除外を継続する。週次勤務は同日内だけとし、日またぎ勤務は廃止する。

従来は勤務枠の展開結果をカレンダーIDごとに保持していた。今回は同じ拠点のどの勤務行IDでも共通の計算になるため、1回の計画データ生成で1回だけ展開し、設備間で使い回す。動作を変えずに重複処理を減らす整理とする。

画面では、カレンダー名と親子設定の一覧から、週次勤務行を直接編集する一覧へ変更する。休日・停止は拠点全体を検索し、新規登録時は代表勤務行へ紐づける。共通フォームに追加した`listScope`は「一覧を検索する条件」であり、保存時の固定値を表す`scope`とは用途を分ける。指定しない既存画面の検索・保存は従来どおりとする。

## 新規DB作成手順

SSMS（SQL Serverを操作する画面）で、次のSQLを順番に実行する。

1. `DataBase/query/create_database_sqlserver.sql`：DBがなければ`TONOPS-SCH`を作成する。
2. `DataBase/query/schema_sqlserver.sql`：テーブル・外部キー・重複防止制約・索引を作成する。
3. `DataBase/query/seed_demo_sqlserver.sql`：パン工場・週次勤務12件・製品6件・オーダー7件・タスク21件・下書き計画2件などを登録する。

Pythonで作成する場合は、バックエンドのルートで次を実行する。

```powershell
python -m DataBase.setup_database
```

Pythonの経路は保存済みSQLを実行せず、モデル定義からテーブルを作成してデモを登録する。手動SQLとPythonのデモ登録はどちらか一方を使う。Python初期設定は登録済みのデモを追加・変更しない。

既存テーブルの列削除・変換は行わず、新規DBを対象とする。`add_plan_name_unique_sqlserver.sql`は既存DB向けの補助SQLで、新規作成には不要。

手動SQLの予定日は既存の2026-10-30基準を維持し、Pythonのデモは実行日の翌日を基準とする。

## 確認する項目

1. 新規作成後に`M_Organizations`・`M_CalendarPatterns`がなく、`M_Calendars`に曜日・時間帯の12行がある。
2. 拠点に保存された`CalendarID`が同じ拠点の勤務行を参照している。
3. カレンダー画面で、曜日・開始終了時刻・勤務名を登録・編集・削除できる。
4. 月～土の午前午後が稼働、12:00～13:00と日曜が非稼働として表示・計算される。
5. 休日・設備停止を登録すると、同じ拠点の該当日時が稼働枠から除外される。例外の開始・終了は日本時間で入力・表示される。
6. 終了時刻が開始時刻以下の勤務は、新規登録・部分更新で拒否される。日中の勤務は指定期間内に切り取って表示される。
7. 代表勤務行を編集・削除した後も、残りの勤務と停止例外が正しく参照される。
8. 製品・設備・オーダーの表示保存、下書き計画の計算、比較・複製・承認が従来どおり操作できる。
9. `docs/Book1.xlsx`をExcelで開き、列名・型・列数・説明・印刷範囲を確認する。

今回の作業ではSQL Serverへの接続、DB作成、仮データ投入を実行していない。実DBの作成結果と画面操作は上記手順で確認する。

## 変更したファイル

バックエンドのルートからの相対パス。既存ファイルを更新し、この変更記録だけ新規追加する。

| ファイル | 更新した処理 |
|---|---|
| `DataBase/query/create_database_sqlserver.sql` | 新しい構成と実行順の説明 |
| `DataBase/query/schema_sqlserver.sql` | 組織・パターン削除、勤務列統合、関連列・制約変更 |
| `DataBase/query/seed_demo_sqlserver.sql` | 週次勤務12行の直接登録、代表ID、空DB判定 |
| `DataBase/setup_database.py` | 新モデルの初期作成、拠点名によるデモ登録済み判定 |
| `app/models/masters.py` | 新テーブル・列・外部キー・重複防止条件 |
| `app/models/__init__.py` | 廃止モデルの読込み除去 |
| `app/services/calendar_service.py` | 拠点共通勤務・停止の取得、入力確認、参照の自動設定・付け替え |
| `app/services/worktime.py` | 週次勤務の展開、停止例外の差引き、旧有効期間・追加稼働分岐の削除 |
| `app/services/demo_seed.py` | 組織を作らない初期登録、カレンダーへの勤務直接登録 |
| `app/engine/snapshot.py` | `Location.CalendarID`参照、拠点共通勤務の重複展開削減 |
| `app/routers/crud.py` | 関連テーブルを使う一覧検索を任意で追加できる仕組み |
| `app/routers/masters.py` | 廃止API削除、新しい保存・削除・検索処理の接続 |
| `tests/test_order_crud.py` | 組織なしの共通準備、カレンダー9件追加、既存オーダー19件維持 |
| `README.md` | 現行構成と初期登録判定・カレンダー説明 |
| `docs/SYSTEM_OVERVIEW.md` | 現行の列定義・関連図・API・画面対応 |
| `docs/DB_SCHEMA_UPDATE_20261111.md` | 今回の変更理由・実行手順・確認結果 |

フロントエンドのルートからの相対パス。

| ファイル | 更新した処理 |
|---|---|
| `docs/Book1.xlsx` | 全23テーブル282列の定義・説明・書式・印刷範囲 |
| `src/app/components/main/calendars/calendars.component.ts` | 拠点共通の勤務・停止・稼働時間確認画面 |
| `src/app/components/main/resources/resources.component.ts` | 拠点共通カレンダー候補と既存指定の表示 |
| `src/app/components/common/forms/master-editor.component.ts` | 一覧専用の検索条件を使用する取得処理 |
| `src/app/interfaces/master.interface.ts` | 拠点の代表勤務行IDの型定義 |
| `src/app/interfaces/master-editor.interface.ts` | 廃止APIの除去、一覧専用検索条件の型定義 |
| `src/app/services/master-catalog.service.ts` | 拠点に所属する代表勤務行の選択を共通化 |
| `src/app/services/master-reference.service.ts` | 自動付け替えへ移した勤務行の旧削除ガード除去 |
| `src/app/services/page-hints.ts` | 画面案内を休日・停止の仕様へ変更 |
| `README.md` | 新カレンダー構成と画面・API対応 |

## カレンダー統合時に実施した確認（夜勤廃止前）

- Python変更10ファイルの構文確認が成功。
- PythonモデルとSQLの全23テーブル282列について、列名・列順・型・NULL可否・制約名が一致。
- Book1.xlsxとSQLの列定義が一致。ExcelのZIP/XML構造・結合セル74件・印刷範囲を確認。
- 対象外の仮データINSERT125件が変更前と一致。
- メモリ内のSQLiteで既存オーダー・マスタ操作19件とカレンダー操作9件、計28件が成功。
- 午前午後の休憩、停止時間の差引き、前日から続く夜勤の期間切取りが成功。
- 初期データは拠点1・勤務12・製品6・製品工程18・実行候補18・設備6・オーダー7・タスク21・下書き計画2件。
- 計画計算へ渡すデータで昼休み・日曜休み・設備共通勤務を確認し、勤務展開が1回であることを確認。
- Python初期作成処理をメモリDBで2回実行し、2回目にデータが増えないことを確認。

検証用Pythonには`pydantic-settings`が未導入のため、API・モデル・初期作成処理の確認時は設定取得だけをテスト用の固定値へ差し替えた。本番コードの設定読込みは変更していない。SQL Serverでの作成・実行、同時操作時のロック動作、ブラウザーでの画面操作は未確認。外部通信、ビルド、解析コマンド、Git操作は実行していない。

## 夜勤機能の削除（2026-11-11追記）

週次勤務の開始・終了の列名はStartTime・EndTime、型はTIMEを維持する。
変更前は終了が開始以下の勤務を翌日終了としていた。変更後はEndTime > StartTimeの同日勤務だけを登録・計算する。
画面とAPIの新規・部分更新で確認し、Pythonモデルと新規作成SQLにも同じ制約を追加する。
既存の不正な勤務を読み込んだ場合は、勤務行IDを含むエラーを返して修正対象を示す。

前日からの勤務を調べる走査と翌日終了への繰越を削除し、API保存時と読込時の時刻確認を共通関数へまとめた。
午前・午後の複数勤務、昼休み、日曜休み、日本時間保存、曜日0～6、複数日にまたがる休日・停止は維持する。
休日・停止のStartTime・EndTimeは日時型のままで、複数日停止を制限しない。
デモの勤務はすべて同日内なので仮データの内容は変更しない。

今回の変更対象：

```text
バックエンド:
app/services/worktime.py
app/services/calendar_service.py
app/models/masters.py
tests/test_order_crud.py
DataBase/query/schema_sqlserver.sql
README.md
docs/SYSTEM_OVERVIEW.md
docs/DB_SCHEMA_UPDATE_20261111.md
docs/DATETIME_JST.md
docs/WEEKDAY_NUMBERING.md

フロントエンド:
src/app/components/main/calendars/calendars.component.ts
README.md
docs/Book1.xlsx（勤務終了の説明2セル）
```

実DBへの接続・更新は行っていない。新規作成SQLの制約は既存DBへ自動追加されない。
画面では09:00～12:00と13:00～18:00の保存・表示、12:00～12:00と22:00～06:00の登録拒否、停止日時の差引きを確認する。

今回の確認結果：

- Python変更4ファイルをpython -m py_compileで構文確認。
- アプリ設定・DB接続を使わず、実際の勤務計算で6ケースを確認。日中の複数勤務・昼休み・期間切取り・停止差引き・複数日停止・翌日への持越しなしを確認。
- 共通の勤務時刻検証で5ケースを確認。同日勤務を許可し、逆転・同時刻・時差付き時刻を拒否。不正な既存勤務にはIDを含むエラーを返すことを確認。
- 画面・API・モデル・SQLが同日内のEndTime > StartTimeで一致することを読み合わせ。
- 設計ExcelはF21/G21以外のセル値・書式・結合・印刷範囲・倍率を維持。
- API操作用の既存テストを更新したが、今回はDBを使うテストとブラウザー操作は実行していない。SQL Server接続、ビルド、解析コマンド、Git操作、外部通信も実行していない。


## 作業者4マスタ追加（2026-11-11追記）

作業者・全工程リンク・週次勤務・不在の4表31列を追加し、全27表313列へ更新した。
詳細は[作業者マスタ追加仕様](WORKER_MASTERS.md)を参照。旧23表282列の照合結果は追加前の記録。
