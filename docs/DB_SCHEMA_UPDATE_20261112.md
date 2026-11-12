<!-- 2026-11-12のDB・API・画面・Excelの変更内容、初期設定と確認手順を記録する資料。 -->
# DB定義の更新（2026-11-12）

新規DB用のSQL、Python初期設定、バックエンド、Angular画面、フロントエンドの`docs/Book1.xlsx`を25テーブル・283カラムに揃えた。
以下はコードとメモリDBで確認した仕様。実SQL Serverへの接続・作成とブラウザー操作は行っていない。

## 変更前後

| 対象 | 変更前 | 変更後 |
|---|---|---|
| M_Resources | ResourceTypeとCalendarIDを保持 | 両列を削除。グループはResourceGroupID、勤務はLocationIDから所属拠点を参照 |
| M_CalendarExceptions | StartTime・EndTime | StartAt・EndAt。日時の型と日本時間は維持 |
| 作業者の担当設定 | M_WorkerProcessesLink・WorkerProcessLinkID | M_WorkerSkillMap・WorkerSkillMapID。既存の担当生成処理も新名称を使用 |
| T_Plans | HorizonStart・HorizonEnd | StartAt・EndAt |
| T_SolverRunResult | StartedAt・FinishedAt・TimeLimitSec | StartAt・EndAt。TimeLimitSecは削除 |
| M_CalculationSettings | TimeLimitSecで計算を打ち切る | 列・既定値・依頼時の指定を削除し、探索時間の上限を設けない |
| T_WorkActuals | WorkDate・WorkHours・Source・ExternalKeyを保持 | 4列を削除。日付・時間は開始終了から求める |
| T_WorkActuals.Status | IN_PROGRESS・DONE・SUSPENDED。既定値DONE | NULL＝作業中、DONE＝完了、SUSPENDED＝中断。既定値なし |

開始日時の実際の旧列名は`StartedAt`であり、`StartedAtt`ではなかった。
変更する日時のDB型はすべて`DATETIME2(7)`を維持する。
週次勤務の`M_Calendars.StartTime・EndTime`と`M_WorkerCalendars.StartTime・EndTime`は、日時ではなく時刻なので変更しない。

## 実装の意図

設備の勤務は既に拠点共通だったため、設備個別のカレンダー選択・画面上のID補正・代表勤務行削除時の設備参照更新を削除した。
拠点と停止例外の参照付け替え、昼休みや休日の除外、曜日番号（日曜0～土曜6）、勤務未登録時の常時稼働は維持する。

計算時間上限は履歴だけでなく、設定・API・計算内部からも取り除いた。探索は最適性の判定またはキャンセルまで続く。
時間の経過割合から作っていた進捗バーは、待機中・探索中の状態表示へ変更した。解の件数・評価値の表示とキャンセル操作は維持する。
新しい解が見つからない間も中止要求を確認できるよう、計算とは並行して監視する処理を追加した。

作業実績は次の組合せをDB制約（保存できる値を決める条件）で確認する。

| 作業状態 | EndAt | Status |
|---|---|---|
| 作業中 | NULL | NULL |
| 完了 | 開始以降の終了日時 | DONE |
| 中断 | 開始以降の終了日時 | SUSPENDED |

終了日時だけ、または完了・中断だけの保存は受け付けない。既存の実績によるオーダー編集・タスク再生成の保護は維持する。
未実装の実績CRUD（取得・登録・更新・削除）は追加せず、画面の開始・完了操作が`T_Tasks.Status`を更新する既存の範囲を維持する。

## APIと画面

- 計画の作成・取得・一覧・比較・ボード、停止例外、計算実行の日時項目は`startAt`・`endAt`へ統一した。
- リソースの`resourceType`・`calendarId`と計算依頼の`timeLimitSec`を削除した。
- 通常APIの日時は`+09:00`付きの日本時間、ボードの日時は時差表記なしの日本時間を維持する。
- 作業者マスタの新しい画面・CRUD API・計算制約は追加しない。

Excelは変更列・説明・NULL可否・カラム数を更新した。以前廃止済みの`T_TaskDependencies`・`T_TaskResourceOptions`の定義も取り除き、現在のモデルに揃えた。
既存の書式・列幅・結合セル・印刷範囲などのExcel情報は保持し、削除した行に合わせて結合セル・印刷範囲を移動した。

## DB作成

Pythonで作成する場合は、バックエンドのルートで以下を実行する。

```powershell
Set-Location -LiteralPath 'C:\Users\taisei_fujita\Desktop\TONOPS-SCH-backend\TONOPS-SCH-backend'
python -m DataBase.setup_database
```

DBがなければ作成し、現在のモデルでテーブルを作り、仮データを投入する。デモ登録済みの場合は既存データを保持し、重複投入しない。
今回のようにDBを削除した状態なら、新しい定義で作成できる。既存DBの列を改名・削除する機能は持たない。

SSMSで作成する場合は、次の順に実行する。Python版とSQL版は代替手段なので、初期データの投入はどちらか一方で行う。

1. `DataBase/query/create_database_sqlserver.sql`
2. `DataBase/query/schema_sqlserver.sql`
3. `DataBase/query/seed_demo_sqlserver.sql`

Python版は実行日の翌日06:00を予定の基準にする。SQL版は従来どおり2026-10-31 06:00を基準とする。
両方式ともパン6製品・製品工程18件・オーダー7件・タスク21件・下書き計画2件・作業者3人・スキルマップ54件・作業者勤務36件・不在1件を登録する。

## 変更ファイル

バックエンドのルートからの相対パス。

```text
DataBase/setup_database.py
DataBase/query/schema_sqlserver.sql
DataBase/query/seed_demo_sqlserver.sql
app/models/masters.py
app/models/transactions.py
app/models/__init__.py
app/engine/problem.py
app/engine/snapshot.py
app/engine/model_builder.py
app/engine/cancellation.py（追加）
app/engine/solve.py
app/worker.py
app/routers/masters.py
app/routers/plans.py
app/services/calendar_service.py
app/services/board_service.py
app/services/compare_service.py
app/services/demo_seed.py
app/services/plan_service.py
app/services/plan_lifecycle.py
app/services/product_process_service.py
app/services/worker_process_service.py
tests/test_order_crud.py
tests/test_task_conditions.py
tests/test_schema_updates.py（追加）
docs/WORKER_MASTERS.md
docs/SYSTEM_OVERVIEW.md
docs/DB_SCHEMA_UPDATE_20261112.md（追加）
README.md
```

フロントエンドのルートからの相対パス。

```text
src/app/interfaces/master.interface.ts
src/app/interfaces/plan.interface.ts
src/app/interfaces/board.interface.ts
src/app/interfaces/compare.interface.ts
src/app/services/api.service.ts
src/app/components/main/resources/resources.component.ts
src/app/components/main/calendars/calendars.component.ts
src/app/components/main/plans/plans.component.ts
src/app/components/main/plans/forms/plan-create-form.component.ts
src/app/components/main/dashboard/dashboard.component.ts
src/app/components/main/plan-board/plan-board.component.ts
src/app/components/main/plan-compare/plan-compare.component.ts
docs/Book1.xlsx
README.md
```

## 確認結果と確認する操作

メモリDBで41件のテストが成功した。設定ライブラリ`pydantic-settings`が検証用Pythonにないため、テスト実行中だけ設定の基底クラスを代替し、実際の設定ファイル・実DB・外部通信を使わずに確認した。アプリ本体の設定処理は変更していない。

- Python版とSQL版の仮データ投入、作業者スキル54件・タスク21件・計算用工程条件の読込み。
- オーダーの登録・編集・削除、実績・既存割付がある場合の編集・再生成保護。
- カレンダーの登録・停止・代表行削除、日本時間、日曜0～土曜6、別拠点混入の防止。
- 設備に個別カレンダーがなくても、同じ拠点の全設備へ勤務・停止が反映されること。
- 新しい日時項目での計画作成・複製・比較・承認・ボード表示。
- 時間上限なしの計算依頼、重複依頼の拒否、キャンセルの受付、中止監視。
- 実績の作業中・完了・中断の保存と、日時・状態が食い違う保存の拒否。

検証用Pythonには`ortools`もないため、実際の最適化計算は実行していない。SQL Serverでの作成・ブラウザー操作・ビルドも未実行。
Python53ファイルの構文を確認し、モデル・SQL・Excelの25テーブル・283列について列名・NULL可否が一致すること、SQLの型がモデルと一致することも照合した。ExcelのZIP・XML・行番号・セル番地も確認した。

利用環境では、DB作成後に次を確認する。

1. リソース画面で名称・グループ・同時作業数を登録・編集できること。
2. カレンダーの勤務と停止例外が、同じ拠点の設備へ反映されること。
3. 計画の作成・一覧・比較・複製・承認で開始終了が正しく表示されること。
4. 計算設定名に秒数が表示されず、計算実行中の状態・解の件数が表示されること。
5. 計算のキャンセル後に探索が止まり、結果と計画の状態を確認できること。
