# 日単位計画モード（日次バケット方式）仕様・変更記録（2026-11-24）

従来の分単位計算（`TimeUnit = 'MINUTE'`、設備ベースの時刻スケジューリング）をそのまま維持しつつ、センシング事業部向けに **日単位計算モード（`TimeUnit = 'DAY'`、作業者×稼働日の日次バケット方式）** を追加した。アプリの既定の計算時間単位は `DAY` とする。

---

## 1. DB構成の変更（全25テーブル・278カラム）

| テーブル | 変更種別 | 内容 |
| --- | --- | --- |
| `M_ProcessGroups` | 新規テーブル | 工程区分マスタ（`ProcessGroupID`, `LocationID`, `ProcessGroupName`, `SortOrder`, 監査列, `DeleteFlag`）。拠点内で区分名重複不可。 |
| `M_CalculationSettings` | 既定値変更 | `TimeUnit` の既定値を `'MINUTE'` から `'DAY'` へ変更。 |
| `M_Product` | カラム追加 | `ExcludeFromDailyCap`（`BIT NOT NULL DEFAULT 0`）。部品分譲など1日作業台数上限から除外する製品を指定。 |
| `M_ProductProcesses` | カラム追加 | `ProcessGroupID`（FK `M_ProcessGroups`）、`StandardOffsetDays`（出荷日からの標準前倒し稼働日数）、`DurationDays`（所要稼働日数、既定1）、`MinLagDays`（最小稼働日間隔、既定0）、`MaxLagDays`（最大稼働日間隔）。作業時間合計0分の登録を許可。 |
| `M_Workers` | カラム追加 | `MaxDailyQuantity`（`NUMERIC(18,3) NULL`）。作業者の1日作業台数上限（NULLは上限なし）。 |
| `T_Orders` | 制約撤廃 | `UQ_T_Orders_LocationID_WBSNumber` 一意制約および保存時のWBS重複チェックを撤廃。同一WBS番号を小分け単位の複数オーダーとして登録可能。 |
| `T_PlanAssignments` | 制約変更 | `ResourceID`・`WorkerID` をともにNULL許可とし、`CK_T_PlanAssignments_ResourceOrWorker`（どちらか一方以上必須）を追加。分モードは `ResourceID`、日モードは `WorkerID` を使用。 |

---

## 2. 日次バケット計算の業務ルール

- **対象モード判定**：計画に紐づく `M_CalculationSettings.TimeUnit == 'DAY'` のとき日次バケット方式（`app/engine/day_*.py`）、`'MINUTE'` のとき従来の分単位方式（`app/engine/model_builder.py` 等）を実行する。
- **稼働日軸と作業者カレンダー**：
  - 拠点の `M_Calendars` と `M_CalendarExceptions` から稼働日を展開する。
  - 作業者の `M_WorkerCalendars` から拠点・本人の例外休日を差し引き、**通常勤務時間が1分でも残る日は出勤可能（半休は出勤扱い）、すべて覆われた日のみ不在**とする。
- **1日作業台数上限のカウント**：
  - 同一オーダー×同一工程区分（`ProcessGroupID`）の中で **`SequenceNumber` が最小の先頭工程のみ** 1日台数上限へカウントする（二重計上防止）。
  - `M_Product.ExcludeFromDailyCap = 1`（部品分譲など）は上限カウント対象外とする。
- **同一工程区分の同一作業者制約・オーダー作業者指定**：
  - 同一オーダー内で同じ `ProcessGroupID` に属する工程は同一作業者へ割り当てる。
  - `T_OrderWorkers` に指定作業者がいる場合、スキルマップ（`CanExecute = 1`）と重なる工程区分はその指定作業者へ候補を絞り込む。
- **工程間の稼働日間隔**：同一オーダーの隣接工程で `MinLagDays` / `MaxLagDays` を守る。
- **標準作業日の逆算と分散方向**：
  - 出荷日（`T_Orders.ShippingDate`、未指定時は `DeadLine`）から `StandardOffsetDays` 稼働日前を標準作業日とする。
  - 1日上限超過時は **前倒しを優先**（重み 100/日）し、後ろ倒し（重み 300/日）は **出荷日 − 1稼働日まで許容** する。出荷日当日以降は納期遅れ（超重ペナルティ）として回避する。
- **割付の保存形式**：日モードの割付は `ResourceID = NULL`、`WorkerID = 担当作業者ID`、`StartAt = 開始稼働日 00:00:00`、`EndAt = 終了稼働日の翌日 00:00:00`、`SetupMinutes = 0` で保存する。

---

## 3. API・画面の対応

- **マスタAPI**：`/api/v1/process-groups` CRUD（参照中の区分は 409 で削除保護）。
- **計画ボードAPI（`GET /api/v1/plans/{planId}/board`）**：
  - `plan.timeUnit` を返却する。
  - `TimeUnit = 'DAY'` のときは、作業者行・作業者イベント・作業者不在日に加え、Excel風オーダー一覧と作業者別・日別台数サマリを含む `dailyView` を返却する。
- **手動編集API（`POST .../assignments/validate`、`PATCH .../assignments`）**：
  - `AssignmentChange` に `workerId` を追加。日モードでは作業日・担当作業者・固定・割付解除・未割付配置を検証・保存する。
- **割付一覧API（`GET /api/v1/plans/{planId}/assignments`）**：
  - `Resource`・`Worker` と外部結合し、`workerId` / `workerName` も返却する。
- **計画比較API（`GET /api/v1/plans/compare`）**：
  - 日モード計画同士の比較で作業者名・担当変更・日数シフトを表示する。
- **フロントエンド画面**：
  - 計画ボード：日モードでは「一覧（Excel風）」（作業者別・日別台数サマリ＋オーダー×工程の日付表）と「作業者ボード」（日単位ガント）をタブ切替でき、右パネルから作業日・担当作業者を直接編集できる。
  - 製品・工程画面：上部に折り畳み可能な「工程区分」マスタを配置し、製品の「日上限除外」と工程の日次項目を編集可能。
  - 作業者画面：「1日の作業台数上限」を編集可能。
  - 計算設定画面：新規登録時の時間単位既定値を「日」に変更。

---

## 4. DB再作成手順

既存DBを削除した後、バックエンドのルートフォルダで以下を実行する。

```powershell
python -m DataBase.setup_database
```

- パン工場（`LocationID = 1`）：`TimeUnit = 'MINUTE'` の既存デモデータを維持する。
- センシング事業部（`LocationID = 2`）：`TimeUnit = 'DAY'`、3工程区分（組立・電気調整・調整検査）、6作業者（本間15・岩佐20・伴10・清川10・藤川10・上田8）、部品分譲を含む5製品・18工程・60勤務行・108スキル行を登録する。
