<!-- 日本時間保存への変更理由・入出力契約・変更ファイルと確認方法を説明する資料。 -->
# 日時の日本時間統一

> 現行仕様の追記（2026-11-11）：夜勤を廃止し、週次勤務は同日内のEndTime > StartTimeだけを受け付ける。以下の夜勤に関する記載は廃止前の変更記録。

DBは再作成する。既存のUTCデータの移行・実DBの削除・作成・接続は今回実行しない。
バックエンドのルートで `python -m DataBase.setup_database` を実行すると、新しい定義でDB・テーブル・仮データを作成する。SSMSのSQL3本を使う方法も同じ仕様。

## 型と登録値

- 日付のみはDATE、週次勤務の時刻のみはTIMEを維持する。
- 日付と時刻を持つ列はDATETIME2(7)へ表記を統一する。SQL ServerではDATETIME2も既定で小数秒7桁のため、保存精度そのものは変わらない。
- DATETIME2(7)は時差を保持しないため、アプリ全体で保存値を日本時間と定義する。
- Python日時は小数秒6桁まで、現在日時の自動登録は従来と同じ秒単位。DBの桁数を指定しても値の精度が自動的に増えるわけではない。

| 箇所 | 日本時間09:00を入力した場合 |
|---|---|
| DB | 2026-11-11 09:00:00.0000000 |
| 通常API | 2026-11-11T09:00:00+09:00 |
| 画面 | 2026/11/11 09:00 |

時差なしのAPI入力は日本時間とする。Zや別の時差を明示した入力は、その実時点に対応する日本時間へ揃える。DBへUTC値は保存しない。
ボード用の描画データは、既存部品に合わせて時差表記なしの日本時間を維持する。日時の値自体をずらす処理は不要になる。

## 変更前の問題と変更内容

従来はDBと通常APIがUTC、入力・表示が日本時間で、同じ時刻がDBと画面で9時間異なって見えた。
登録・更新・計算要求・承認・計算開始終了日時も含め、全ての保存値を日本時間へ統一する。

- `jst_now`はOSの時差に依存せず、日本時間の現在日時を作る。
- `to_jst_naive`はAPIの時差付き入力を日本時間へ揃え、DB用に時差表記を外す。
- `as_jst`はDBの値に+09:00を付ける。表示時に9時間を加算しない。
- `JstDatetime`は全日時列のAPI入力確認と出力形式を共通化する。
- 画面の`jstDateTime`は入力した日本時間に+09:00を付けて送る。未変更の入力は送信しない既存処理を維持する。
- 共通処理に統一したため、旧UTC変換の重複処理・不要な時差引数を削除する。
- SQL仮データは従来のUTC値に9時間を加え、元と同じ実時点の日本時間として保存する。TIME・DATEの値は変更しない。
- Book1.xlsxの型・説明・保存値の例も同じ日本時間へ揃える。

## 既存機能への影響と確認観点

画面に表示する時刻、勤務時間、昼休み、夜勤、日曜休み、計画の期間・所要分数は維持する。
主キー・外部キー・製品工程・オーダー・タスクの構成は変更しない。
日付をまたぐ入力、日本時間とUTCを明示した入力の同一性、小数秒保持、休日停止の適用、計画ボード・比較を確認する。
既存UTC値の入ったDBでは初期設定を再実行しても日時の変換は行わないため、了承済みのDB再作成を前提とする。

## 検証

- Pythonの構文確認。
- メモリDBの既存操作28件と日本時間専用2件。
- 仮データの日本時間06:00開始、昼休み・日曜休み、計画ボード表示と計画比較。
- フロント日時関数の09:00入力→09:00+09:00送信→09:00表示、不正日付の拒否。
- SQL・モデル・Book1.xlsxの型定義照合、ブックのXML・結合・書式を保持。

検証環境にはpydantic-settingsがないため、DB・API検証は設定取得だけを固定値へ差し替えて実施する。実SQL Serverでの作成、OR-Toolsでの最適化実行、ブラウザー画面操作は未実施。外部通信を伴うコマンド、ビルド、解析コマンド、Git操作は実行しない。

## 変更ファイル

### バックエンド

- `DataBase/query/schema_sqlserver.sql`
- `DataBase/query/seed_demo_sqlserver.sql`
- `README.md`
- `app/core/timeutil.py`
- `app/engine/problem.py`
- `app/engine/result.py`
- `app/engine/snapshot.py`
- `app/engine/solve.py`
- `app/models/base.py`
- `app/models/masters.py`
- `app/models/transactions.py`
- `app/models/types.py`
- `app/routers/masters.py`
- `app/routers/plans.py`
- `app/schemas/base.py`
- `app/services/board_service.py`
- `app/services/calendar_service.py`
- `app/services/compare_service.py`
- `app/services/demo_seed.py`
- `app/services/edit_service.py`
- `app/services/plan_lifecycle.py`
- `app/services/plan_service.py`
- `app/services/worktime.py`
- `app/worker.py`
- `docs/DATETIME_JST.md`
- `docs/DB_SCHEMA_UPDATE_20261111.md`
- `docs/SYSTEM_OVERVIEW.md`
- `tests/test_order_crud.py`

### フロントエンド

- `README.md`
- `docs/Book1.xlsx`
- `src/app/components/common/forms/master-editor.component.ts`
- `src/app/components/main/calendars/calendars.component.ts`
- `src/app/components/main/dashboard/dashboard.component.ts`
- `src/app/components/main/orders/forms/order-form.component.ts`
- `src/app/components/main/orders/orders.component.ts`
- `src/app/components/main/plans/plans.component.ts`
- `src/app/interfaces/index.ts`
- `src/app/interfaces/master-editor.interface.ts`
- `src/app/services/format.ts`
- `src/app/services/master-form.ts`

