# 実装フェーズ

> フェーズ 4 までは 1 つのリポジトリ（`backend/` と `frontend/`）で開発し、その後
> [TONOPS-SCH-backend](https://github.com/tds-dev/TONOPS-SCH-backend) と
> [TONOPS-SCH-frontend](https://github.com/tds-dev/TONOPS-SCH-frontend) に分割しました（コミット履歴はそれぞれに残っています）。
> 本書のパスは分割前の構成（`backend/…`、`frontend/…`）で書かれています。

各フェーズの最後に git コミットします（`git log --oneline`）。対象はスケジューリングの
コア機能のみ。認証、外部連携（SynViz、工程くん）、複数拠点の切替は後で追加します。

## フェーズ1 — バックエンド基盤 ✅

* 26 テーブルの SQLAlchemy モデル（`app/models/`）。命名はドラフト設計書どおり。
  未作成: `M_Users`、`T_ExternalLinks`、`T_SyncRuns`、`T_ImportBatches`、`T_AuditLog`。
* 汎用 CRUD ルーター（`app/routers/crud.py`）: 列による絞り込み付き一覧、取得、登録、
  部分更新、論理削除。スキーマはモデルから生成（`app/schemas/base.py`）。
* カレンダー: 週次パターン＋例外＋親カレンダー → UTC の稼働区間
  （`app/services/worktime.py`、`GET /calendars/{id}/working-time`）。
* `POST /jobs/{id}/generate-tasks`: 工程ルート → タスク、リソース候補
  （段取り＋固定＋数量×単位当たり時間）、工程のラグ付き FS 依存関係。
* デモデータ（`DataBase/setup_database.py`）: 3 グループ 6 設備、品目 6、オーダー 7、
  系統別の段取り替えマトリクス、曜日ルール 1 件、既定の計画プロファイル。

## フェーズ2 — スケジューリングエンジン ✅

* `engine/problem.py`: ソルバーへの入力を素のデータで表現（計画期間開始からの分）。
* `engine/snapshot.py`: DB → Problem（カレンダー、グループ候補、ロック、ヒント、ルール）。
* `engine/model_builder.py`: CP-SAT モデル
  * 代替リソース、カレンダーはブロック区間（タスクは 1 つの稼働枠内に収める）
  * FS/SS/FF/SF 依存関係（最小・最大ラグ）
  * `AddCircuit` による順序依存の段取り替え。禁止の組合せにはアークを張らない
  * ロック済みタスクは固定。前回計画をヒントに使用（REPAIR は安定性ペナルティ付き）
  * 目的関数: 優先度で重み付けした納期遅れ、未割付タスク、段取り、最終完了時刻
* `engine/rules/`: プラグインのレジストリ。組込みは `allowed_weekdays`。
* `engine/evaluate.py`: 純粋なチェッカー → 違反（日本語メッセージ）と KPI。
* `engine/solve.py` + `app/worker.py`: 待機中の `T_SolverRuns` を実行し、割付・KPI・
  違反を書き込む。進捗は `ProgressJSON`。キャンセル対応。
* API: `POST/GET /plans`、`POST /plans/{id}/solve`（開発用に `wait: true`）、
  `GET /solver-runs/{id}`、`POST /solver-runs/{id}/cancel`、
  `GET /plans/{id}/assignments|kpis|violations`、`GET /rule-types`。

設計メモ:
* `T_PlanAssignments.StartAt–EndAt` はタスク本体。`SetupMinutes` は `StartAt` の
  **直前**に置く段取り替え（ボードではグレーのブロックで表示）。
* 候補ごとの段取り（例: 充填準備 15 分）は `DurationMin` に含む。
* タスクはまだ休憩をまたいで分割しない。どの稼働枠より長いタスクは未割付として報告する。
* `RowVer` は整数のバージョンカウンタ（SQLite に移植可能）。`rowversion` ではない。
* アクションのパスは `:approve` ではなく `/approve` 形式。

## フェーズ3 — 計画のライフサイクルと編集 API ✅

* `services/plan_lifecycle.py`
  * 承認: DRAFT → MASTER。拠点行をロックして 1 トランザクションで実行。重なる MASTER は、
    新計画の開始より前に始まっていれば SUPERSEDED（`SupersededAt` = 新計画の開始）、
    そうでなければ DISCARDED。割付のあるジョブは OPEN → PLANNED。
    未割付以外の必須違反がある場合は `force: true` なしでは承認不可。
  * 破棄（DRAFT → DISCARDED）、複製（割付ごとコピーした新しい DRAFT）。
  * マスタ計画の割付 = MASTER の割付 ＋ SUPERSEDED 計画の `SupersededAt` より前の割付。
* `engine/edit.py`（純粋関数）: 手動変更の適用、変更したリソースの段取り再計算、
  変更前後の違反の差分（新たに発生した違反だけを返す）。
* `GET /plans/{id}/board`: DayPilot 用に整形したデータ（拠点の現地時刻）。
  リソース行（グループ見出し付き）、イベント（段取りは別イベント）、非稼働時間、課題の有無。
* `POST /plans/{id}/assignments/validate`: 保存せずに変更を検証。
* `PATCH /plans/{id}/assignments`: 移動・リサイズ・ロック・解除・未割付タスクの配置。
  `rowVer` による楽観的排他制御（不一致は 409）。新たな必須違反は `force: true` なしでは 422。
  手動で動かしたタスクは既定でロックされ、Source は MANUAL。KPI と違反を再計算。
* `GET /plans/compare?a=&b=`: KPI 差分（良化・悪化）と、差異のあるタスク一覧。
* `GET /dispatch?siteId=&date=`: マスタ計画の配台表（リソース別、開始順）。
* `GET /solver-runs/{id}/events`: 進捗の Server-Sent Events。
* `T_PlanViolations` に `ViolationCode` 列を追加（承認・編集で未割付を区別するため）。
  既存DBの定義変更は別途実施する。新規DBの初期設定は`python -m DataBase.setup_database`で行う。

## フェーズ4 — Angular フロントエンド ✅

Angular 21（スタンドアロンコンポーネント、signal、新しい制御フロー構文）。UI フレームワークは使わず、
デザインキャンバスの青・白のトークンを `src/styles.css` に定義。画面はすべて遅延読み込み。

* `services/`・`interfaces/`（当初は `core/`）: API の型、API クライアント（`api.service.ts`、SSE も含む）、
  拠点の選択（`site.service.ts`、右上のセレクト）、通知、表示用の変換（状態ラベル・日時）、
  API エラーを通知に出すインターセプター。
* ダッシュボード: マスタ計画の KPI、下書きの計画、納期が近いジョブ（3 日以内）、リソース負荷。
* ジョブ: 状態フィルタ・検索、詳細パネル（タスク、割付候補、依存関係）、タスク生成。
* 計画一覧: 新規作成（拠点の現地時刻で入力）、コピー、破棄、2 件選んで比較。
* 計画ボード（`components/main/plan-board/`）:
  * `plan-gantt.component.ts` が DayPilot Lite Scheduler の唯一のラッパー。
    リソースはグループのツリー、段取りは移動できない別イベント、非稼働時間はセルの網掛け、
    色分けは `colorValue` ごとの青系パレット、制約違反はオレンジの枠。
  * ドラッグで移動・リサイズ → `validate` → 適用不可なら元に戻す／必須違反は確認して強制保存 → `PATCH`。
  * 計算実行・部分再計算（SSE で進捗表示、キャンセル可）、承認、マスタとの比較、
    マスタ計画は「コピーして編集」。
  * 右パネル: KPI、選択中タスク（固定・解除、割付を外す）、課題一覧、未割付タスクの配置。
* 計画比較: A/B の KPI カード（改善 = 青、悪化 = オレンジ）、変更タスク一覧、B の承認・A の破棄。
* 配台表: 日付・グループ選択、リソースのタブ、大きな「開始」「完了」ボタン（`PATCH /tasks/{id}`）、
  印刷（全リソースを 1 ページずつ）。
* 実績入力・マスタ編集画面は「準備中」（今後のフェーズ）。
* バックエンドの変更: `POST /plans` のオフセットなしの日時を拠点の現地時刻として扱う（以前は UTC）。

## 補足 — SQL Server を標準に（プロジェクト名 TONOPS-SCH）

* 既定の `DATABASE_URL` をローカル SQL Server（Windows 認証）の `TONOPS-SCH` に変更。
* `DataBase/setup_database.py`: DBと未作成テーブルを作成し、未登録のデモデータを追加する。
* 列型: 文字列は NVARCHAR、日時は DATETIME2（`app/models/types.py`）。SQLite接続にも対応する。

## 補足 — フロントエンドのフォルダー構成を整理

* `components/main/<画面>/`（画面専用の `forms/`・`dialogs/` を含む）、`components/common/{forms,dialogs,select}/`、
  `services/`、`interfaces/` に再編。構成は README を参照。
* 計画作成フォーム・未割付タスクの配置フォームを別コンポーネントに分離。
* ブラウザの `confirm()` を共通の確認ダイアログ（`ConfirmDialogService.ask()`）に置き換え。
* 拠点・リソースグループの選択を共通部品に。`models.ts` を領域別の `*.interface.ts` に分割。

## フェーズ5 — 連携と仕上げ ⏳

CSV 取込、実績とローリング再計画、Docker Compose、E2E 確認。
