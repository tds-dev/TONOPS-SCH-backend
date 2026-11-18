<!-- 属性定義・制約ルールの廃止、製品工程の曜日制限、DB再作成手順を説明する資料。 -->
# 2026-11-13 製品工程の曜日制限への統合

> 本文は当時の変更記録。後続変更で段取り替えを製品工程ID方式へ更新し、タスクの作業番号・集約指定・進捗率・属性を廃止した。現行定義は[SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md)、段取り替えは[専用仕様](PRODUCT_PROCESS_SWITCHES.md)を参照。

現行モデル・新規作成SQL・フロントエンドの `docs/Book1.xlsx` は23テーブル・256カラム。

## DBと計算処理

- `M_AttributeDefinitions` と `M_Rules` を廃止する。
- `M_ProductProcesses` に次の4列を追加する。

| 列 | SQL Server型 | NULL | 初期値・意味 |
|---|---|---|---|
| AllowedWeekdaysJSON | NVARCHAR(MAX) | 不可 | `[0,1,2,3,4,5,6]`。日曜0～土曜6の重複しない整数を1つ以上指定 |
| WeekdayRestrictionEnabled | BIT | 不可 | 1。0は曜日制限だけを無効化し、工程自体は計算対象に残す |
| WeekdayRestrictionStartAt | DATETIME2(7) | 可 | NULLは開始側の制限なし。日本時間の日時 |
| WeekdayRestrictionEndAt | DATETIME2(7) | 可 | NULLは終了側の制限なし。日本時間の日時。開始日時以降 |

適用期間は計画開始日時で判定し、開始・終了の両境界を含む。作業ごとの実行日時で有効状態を切り替える仕様ではない。有効な場合は作業時間全体が禁止曜日に重ならないようにする。曜日番号は既存の勤務カレンダーと共通。

`app/services/task_conditions.py` が最新の工程設定を取得し、`app/engine/weekdays.py` を自動計算と手動編集の検証で共用する。固定作業の扱いも従来の曜日ルールと同じ。作業・割付・実績のIDは変更しない。

`T_PlanViolations.RuleID` は参照先の廃止に合わせて削除する。違反行の識別番号・対象作業・重要度・数値・メッセージと計画コピーは保持する。

`T_Tasks.AttributesJSON`、`M_ProductSwitchTimes`、`M_ProductSwitchRules` は保持する。既存の属性値による段取り替え・禁止順序・ボード色分けも維持する。

## APIと画面

旧 `/attribute-definitions`、`/rules` のCRUD APIと `/rule-types` を廃止する。汎用ルールプラグインと属性条件の照合処理も通常計算から除く。

フロントエンドの `/rules` は既存URLを維持し、画面名を「段取り替え」へ変更する。段取り替えの登録・編集・削除は維持し、旧制約ルールの登録欄・種類取得・曜日専用入力を除く。後続対応で工程の4列を画面から登録・更新する機能を追加した。既存の工程名・順序・待ち時間の編集でも、未送信の曜日設定は保持する。

## 新規DB

DB構成を変更した場合は、DBを削除してから`python -m DataBase.setup_database`でDB・テーブル・仮データを再作成する。手動SQLでは`create_database_sqlserver.sql`→`schema_sqlserver.sql`→`seed_demo_sqlserver.sql`の順で作成する。

デモのくるみパン全工程は平日のみ、他製品の工程は全曜日を許可する。タスクのデモ分類値は段取り替えと色分けのために保持する。

## 確認


画面では製品・工程の既存編集、段取り替えの登録・編集・削除、計画ボードの課題と色分け、計画コピー・承認を確認する。

## 変更ファイル

各リポジトリのルートからの相対パス。既存の汎用登録APIを使うため、工程の4列に新しい専用APIは追加しない。

### TONOPS-SCH-backend

- `app/engine/edit.py`
- `app/engine/evaluate.py`
- `app/engine/model_builder.py`
- `app/engine/problem.py`
- `app/engine/result.py`
- `app/engine/snapshot.py`
- `app/engine/solve.py`
- `app/models/masters.py`
- `app/models/transactions.py`
- `app/models/__init__.py`
- `app/routers/board.py`
- `app/routers/masters.py`
- `app/routers/plans.py`
- `app/services/board_service.py`
- `app/services/demo_seed.py`
- `app/services/plan_lifecycle.py`
- `app/services/product_validation.py`
- `app/services/task_conditions.py`
- `app/engine/rules/allowed_weekdays.py`：削除
- `app/engine/rules/__init__.py`：削除
- `DataBase/setup_database.py`
- `DataBase/query/schema_sqlserver.sql`
- `DataBase/query/seed_demo_sqlserver.sql`
- `docs/PHASES.md`
- `docs/SYSTEM_OVERVIEW.md`
- `docs/WEEKDAY_NUMBERING.md`
- `README.md`
- `app/engine/weekdays.py`：追加
- `docs/DB_SCHEMA_UPDATE_20261113.md`：追加

### TONOPS-SCH-frontend

- `docs/Book1.xlsx`
- `docs/PRODUCT_PROCESSES.md`
- `src/app/app.component.ts`
- `src/app/app.routes.ts`
- `src/app/interfaces/master-editor.interface.ts`
- `src/app/interfaces/plan.interface.ts`
- `src/app/services/api.service.ts`
- `src/app/services/master-form.ts`
- `src/app/services/page-hints.ts`
- `src/app/components/main/rules/rules.component.ts`
- `src/app/components/common/forms/master-editor.component.ts`
- `README.md`

## 後続対応：工程の曜日設定UI・API

製品・工程画面に日曜～土曜のチェックボックス、曜日制限の有効状態、適用開始・終了日時の入力を追加。新規工程は全曜日・有効・期間未指定とする。日時は日本時間で入力し、空欄で期間の指定を解除する。無効化しても保存した曜日と日時は消さない。工程一覧に曜日と有効状態、選択工程の詳細に適用期間を表示する。

既存のモデル連動APIを共用するため、同じデータを保存する専用APIを重複追加しない。

| 操作 | API |
|---|---|
| 一覧 | `GET /api/v1/product-processes?productId=1` |
| 単件取得 | `GET /api/v1/product-processes/{id}` |
| 登録 | `POST /api/v1/product-processes` |
| 部分更新 | `PATCH /api/v1/product-processes/{id}` |

登録・更新で受け付ける曜日設定の例：

```json
{
  "allowedWeekdaysJSON": [1, 2, 3, 4, 5],
  "weekdayRestrictionEnabled": true,
  "weekdayRestrictionStartAt": "2026-11-13T00:00:00+09:00",
  "weekdayRestrictionEndAt": null
}
```

登録時は既存のproductId・sequenceNumber・processNameも指定する。曜日の必須・範囲・重複・期間逆転を検証し、APIでは曜日を番号順に保存する。部分更新で未送信の設定・秒未満の精度・他工程の曜日設定・待ち時間を保持する。


後続対応の主な変更ファイル：

- frontend: `src/app/components/main/products/products.component.ts`
- frontend: `src/app/components/common/forms/master-editor.component.ts`
- frontend: `src/app/interfaces/master-editor.interface.ts`
- frontend: `src/app/services/master-form.ts`
- frontend: `docs/PRODUCT_PROCESSES.md`・`docs/Book1.xlsx`・`README.md`
- backend: `app/services/product_validation.py`
- backend: `docs/DB_SCHEMA_UPDATE_20261113.md`・`README.md`

ブラウザー上の操作、実DBへの保存、OR-Toolsによる自動計算は今回実行していない。ビルド・コードレビュー用コマンド・Git操作・外部通信を伴うコマンドは実行しない。
