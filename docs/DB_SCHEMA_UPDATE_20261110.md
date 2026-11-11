<!-- 2026-11-10のDB構成変更、名称の対応、再作成手順と確認観点を定義する資料。 -->
# DB構成変更（2026-11-10）

既存DBを削除した状態から、新しいDB・テーブル・パン製造デモを作成する構成。
手動実行用SQLとPython初期設定は同じテーブル・列構成を使う。全25テーブル・302カラム。

## 名称と列の変更

| 変更前 | 変更後 |
|---|---|
| M_ChangeoverMatrices / MatrixID / MatrixName | M_ProductSwitchTimes / ProductSwitchTimeID / ProductSwitchTimeName |
| M_ChangeoverEntries / EntryID / MatrixID | M_ProductSwitchRules / ProductSwitchRuleID / ProductSwitchTimeID |
| M_PlanProfiles / ProfileID / ProfileName | M_CalculationSettings / CalculationSettingID / CalculationSettingName |
| T_Actuals / ActualID | T_WorkActuals / WorkActualID |
| T_Orders.OrderNo / DueAt | T_Orders.WBSNumber / DeadLine |
| T_Plans.Memo / ProfileID | T_Plans.Remarks / CalculationSettingID |

IDは1件を指すため単数形を使い、関連テーブルの外部キー（他のテーブルを参照する列）も同じ名前へ変更。
テーブルのT_Orders・T_Plansは既存の複数形を維持する。
T_Orders.ShippingDateはDATETIME2(7)、NULL可として追加し、デモではNULLを登録する。

削除する列はM_Calendars.CalendarCode、M_Locations.LocationCode・TimeZone、M_Organizations.OrganizationCode、M_ResourceGroups.GroupCode、M_Resources.ResourceCode、T_Plans.PlanNo、T_PlanViolations.ViolationCode。
既存SQLでモデルと異なっていた7列の型も統一する。M_CalendarPatterns.StartTime・EndTimeはTIME、M_CalendarPatterns.ValidFrom・ValidTo、M_Rules.ValidFrom・ValidTo、T_WorkActuals.WorkDateはDATEとする。カレンダー展開では時刻、有効期間の判定では日付を受け取る既存処理に合わせる。

削除列に対する一意制約も削除する。WBS番号の拠点内一意制約、計画名の拠点内一意制約は維持する。

## アプリの変更と既存動作の維持

- APIの切替設定・明細・計算設定は `/product-switch-times`、`/product-switch-rules`、`/calculation-settings`。ID・名称も上記に対応するcamelCase形式を使う。
- オーダーの送受信項目は `wbsNumber`、`deadLine`、`shippingDate`。出荷日時は任意入力で、納期による自動計算はDeadLineを使い続ける。
- コード列の入力・表示を削除し、既存のIDと名称で関連付ける。計画はPlanID・PlanNameを使い、計画番号の自動生成を削除する。
- TimeZone列を使わず、アプリ共通のAsia/Tokyoで日時入力・表示・カレンダー展開を行う。通常の日時のUTC保存は維持する。
- 違反コードは計算中の内部分類に残し、DBとAPIから削除する。RuleIDがなくTaskIDが未割付のHARD違反は、これまでと同じく計画承認を妨げない。共通関数で求めたblocksApprovalをボードの課題情報へ返し、画面の警告件数と実際の承認条件を一致させる。
- 製品・工程・実行候補、タスク生成、段取り替え計算、計画の作成・複製・比較・手動割付・承認、実績の有無によるオーダー編集保護を新しい列名へ接続する。
- 初期設定の登録済み判定は、削除した組織コードに代えて共通定数のデモ組織名を使う。

## 追加の6カラム削除

| テーブル | 削除する列 | カラム数の変更 |
|---|---|---|
| M_Resources | CostPerHour、AttributesJSON | 16 → 14 |
| T_Orders | ParentOrderID | 22 → 21 |
| T_Tasks | ParentTaskID、IsMilestone、EffortHours | 19 → 16 |

変更前は、設備単価・設備属性・オーダー／タスクの親ID・節目指定・予定工数をモデルとAPIで保存できる構成だった。これら6列は現在の計算処理へ読み込まれていなかった。
変更後は、作成SQL・仮データSQL・モデル・自動生成されるAPI項目・設計Excelから対象6列を削除し、親IDの参照制約も削除する。全体は308 → 302カラムとなる。

設備属性の入力欄を削除すると専用のattributesField関数の呼出し先がなくなるため、その関数とimportも取り除く。モデルを基にAPI項目を生成する既存方式を使い、定義の重複は追加しない。
既存テストの親オーダー指定は独立した別オーダーへ変更し、対象外データ・数量・日時・タスクの保持確認を維持する。削除項目がAPI応答に含まれない確認を既存テストへ加える。

オーダーとタスクのAttributesJSON、集約指定IsSummaryは維持する。ルールと段取り替えはタスク属性を使い、所要時間は工程候補の準備時間・固定時間・数量当たり時間から求めるため、これらの計算処理は変更しない。
設備の名称・グループ・稼働カレンダー・同時作業数・表示順、およびWBS番号・納期・出荷日時も維持する。

今回追加で変更したファイル：

```text
バックエンド:
DataBase/query/schema_sqlserver.sql
DataBase/query/seed_demo_sqlserver.sql
app/models/masters.py
app/models/transactions.py
tests/test_order_crud.py
README.md
docs/SYSTEM_OVERVIEW.md
docs/DB_SCHEMA_UPDATE_20261110.md

フロントエンド:
src/app/components/main/resources/resources.component.ts
src/app/services/master-form.ts
src/app/services/api.service.ts
README.md
docs/SCH_DB_設計.xlsx
```

画面では設備の登録・編集、オーダーの保存と出荷日時、タスク生成、属性による切替・曜日ルール、計画ボードの表示を確認する。
既存DBへの列削除は実行しない。新規DBを作る場合は下記のSQL実行順を使う。すでに旧構成で作成済みのDBへは、この新規作成SQLによる既存テーブルの列削除は行われない。

## DBの新規作成手順

SSMSで次のSQLを順番に実行する。

1. `DataBase/query/create_database_sqlserver.sql`：DBがなければTONOPS-SCHを作成。
2. `DataBase/query/schema_sqlserver.sql`：新しいテーブル・参照制約・索引を作成。
3. `DataBase/query/seed_demo_sqlserver.sql`：パン工場・製品6件・オーダー7件・タスク21件・下書き計画2件などを登録。

Pythonで作成する場合はバックエンドのルートで `python -m DataBase.setup_database` を実行する。
これは保存済みSQLの読込ではなく、モデル定義からテーブルを作り、Pythonのデモ登録処理を実行する。
手動SQLとPythonは、どちらか一方を使う。Pythonは登録済みデモを追加・変更しない。

手動SQLのデモ予定日は2026-10-30を基準とする既存の固定日付を維持。Pythonのデモは実行日の翌日を基準とする。
`add_plan_name_unique_sqlserver.sql` は既存DB用の補助SQLで、新規作成時には不要。

## 画面で確認する項目

1. 拠点・カレンダー・設備・グループの一覧と編集ができる。
2. WBS番号・納期・任意の出荷日時を保存・再表示でき、出荷日時の空欄も保存できる。
3. 切替時間と切替ルールの親子関係、計算設定の選択が維持される。
4. 下書き計画を計算し、割付・課題・比較・複製・承認を操作できる。
5. 計画ボードと配台表の日本時間が従来どおり表示される。

今回の作業ではSQL Serverへ接続せず、DB作成・仮データ投入は実行していない。実DBでの作成結果と画面操作の確認は、上記手順で行う。

## ソースの照合結果

- SQL・Pythonモデル・設計Excelのテーブル名と302列の名称・NULL可否を照合。
- ExcelとSQLの列順・型も照合。モデルの外部キー参照先とSQLを照合。
- 仮データSQLの141件のINSERTで、列と値の個数、および指定列が作成SQLに存在することを確認。
- バックエンドとフロントエンドのAPI名・項目名を相互に読み合わせ、廃止項目への参照を検索で確認。
- 許可された `python -m py_compile` でPython 48ファイルの構文を確認。最終修正4ファイルも再確認。
- API項目名の変換9件と、共通の承認条件6件をアプリ・DBの読込なしで確認。
- 実DB・実画面・計算結果の実行確認は未実施。ビルド・解析コマンド・Git操作・外部通信は実施していない。

## 変更ファイル一覧

バックエンド（このリポジトリからの相対パス）：

```text
DataBase/query/schema_sqlserver.sql
DataBase/query/seed_demo_sqlserver.sql
DataBase/setup_database.py
README.md
docs/SYSTEM_OVERVIEW.md
docs/DB_SCHEMA_UPDATE_20261110.md
app/core/config.py
app/core/timeutil.py
app/models/__init__.py
app/models/base.py
app/models/masters.py
app/models/transactions.py
app/models/types.py
app/schemas/base.py
app/routers/board.py
app/routers/masters.py
app/routers/orders.py
app/routers/plans.py
app/services/board_service.py
app/services/compare_service.py
app/services/demo_seed.py
app/services/edit_service.py
app/services/order_service.py
app/services/order_validation.py
app/services/plan_lifecycle.py
app/services/plan_service.py
app/engine/model_builder.py
app/engine/problem.py
app/engine/snapshot.py
app/engine/solve.py
tests/test_order_crud.py
```

フロントエンド（TONOPS-SCH-frontendからの相対パス）：

```text
README.md
docs/SCH_DB_設計.xlsx
src/app/interfaces/board.interface.ts
src/app/interfaces/compare.interface.ts
src/app/interfaces/dispatch.interface.ts
src/app/interfaces/index.ts
src/app/interfaces/master-editor.interface.ts
src/app/interfaces/master.interface.ts
src/app/interfaces/order.interface.ts
src/app/interfaces/plan.interface.ts
src/app/services/api.service.ts
src/app/services/format.ts
src/app/services/location.service.ts
src/app/services/master-catalog.service.ts
src/app/services/master-form.ts
src/app/services/master-reference.service.ts
src/app/components/common/forms/master-editor.component.ts
src/app/components/main/calendars/calendars.component.ts
src/app/components/main/dashboard/dashboard.component.ts
src/app/components/main/dispatch/dispatch.component.ts
src/app/components/main/orders/orders.component.ts
src/app/components/main/orders/forms/order-form.component.ts
src/app/components/main/plan-board/plan-board-redirect.component.ts
src/app/components/main/plan-board/plan-board.component.ts
src/app/components/main/plan-board/plan-gantt.component.ts
src/app/components/main/plan-board/forms/assignment-place-form.component.ts
src/app/components/main/plan-compare/plan-compare.component.ts
src/app/components/main/plans/plans.component.ts
src/app/components/main/plans/forms/plan-create-form.component.ts
src/app/components/main/resources/resources.component.ts
src/app/components/main/rules/rules.component.ts
```
