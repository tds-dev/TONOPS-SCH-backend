<!-- 製品マスタから計算時にタスク条件を作る構成と、DB移行・動作確認の手順。 -->
# タスクの設備候補・前後関係を製品マスタから組み立てる

2026-11-12更新。

## 変更前と変更後

| 対象 | 変更前 | 変更後 |
|---|---|---|
| タスク本体 | T_Tasksへ保存 | 維持。TaskID・作業状態・進捗・割付・実績の参照を保持 |
| 設備候補 | T_TaskResourceOptionsへ複製 | テーブルを廃止。M_ProductProcessResourcesから取得 |
| 所要時間 | タスク生成時に計算して保存 | 現在のオーダー数量と工程設備候補から利用時に計算 |
| 前後関係 | T_TaskDependenciesへ保存 | テーブルを廃止。同じ製品の隣接工程をFSで結ぶ |
| 工程間の待ち時間 | タスク生成時に複製 | 前工程のMinLagAfterMin・MaxLagAfterMinを利用時に参照 |
| 製品切替 | M_ProductSwitchTimes・M_ProductSwitchRules | 維持。設備上の直前作業との組合せで求める |

共通処理は`app/services/task_conditions.py`。自動計算、手動配置・移動の検証、ボード、オーダー詳細APIで同じ条件を使う。固定準備を含む所要時間は従来どおり「準備＋固定＋切り上げ（数量×単位当たり時間）」とする。

## 反映のタイミング

- 設備候補・固定時間・数量・待ち時間・工程順は、次回の取得・計算・検証から最新値を使う。保存済みの割付時刻を自動移動する処理は追加しない。
- 作業名・作業番号・表示順・属性はT_Tasksの値を保持する。計算上の前後関係は最新の製品工程順を使う。
- 新しい工程を追加した場合、その工程のタスク本体は従来どおり生成が必要。未生成の工程がある場合は計算・ボード取得時に不足を通知し、不完全な作業一覧で計画を作らない。完了済み・計算対象外の中間工程を飛び越える関係も作らない。
- オーダーごとの候補・待ち時間・FS以外の個別関係の保存は廃止する。製品工程へ紐づかないタスクには候補を返さない。
- 計算は現在のマスタを参照する。過去の条件で再計算するための版管理・履歴保存は、この変更には含めない。

## APIと画面

`GET /orders/{id}/tasks`と`POST /orders/{id}/generate-tasks`は、保存済みタスクと計算した`options`を返す。`optionId`には元の工程設備候補IDを使用する。

`GET /orders/{id}/dependencies`は、計算したFS関係と最小・最大待ち時間を返す。`dependencyId`は後続タスクIDを使う表示用の値で、DBの保存行IDではない。

旧`/task-resource-options`と`/dependencies`の汎用読書きAPIは廃止する。設備候補は`/product-process-resources`、待ち時間・工程順は`/product-processes`で編集する。

オーダー詳細の所要時間は固定準備を含む合計で、「準備○分を含む」と表示する。設備削除前の参照確認も、工程設備候補と既存割付を確認する方式に揃える。

## DB作成・移行

新規DBは`python -m DataBase.setup_database`、または`create_database_sqlserver.sql`→`schema_sqlserver.sql`→`seed_demo_sqlserver.sql`で作成する。どちらも旧2テーブルを作らず、製品工程の候補・時間・待ち時間だけを登録する。
モデルと新規作成SQLのテーブル名・列名・列順は25テーブル・291カラムで一致を確認した。

現在の製品工程構成を持つ既存DBには、`DataBase/query/remove_task_condition_tables_sqlserver.sql`を更新後のアプリと併せて適用する。計算対象のタスクが所属オーダーの製品工程へ紐づいているか確認してから、旧2テーブルだけを削除する。旧テーブルの個別変更は移行しない。タスク本体・計画・割付・違反・実績・製品マスタは保持する。初期設定の`create_all`だけでは既存テーブルを削除しない。

## 確認する操作

1. タスク生成後に工程の設備候補と固定時間を変更し、タスク再生成なしで詳細表示と次回の計算へ反映されること。
2. 工程順と最小・最大待ち時間を変更し、新しい順序で自動計算・手動編集の検証が行われること。
3. 未割付タスクを配置し、最新の候補と所要時間が使われること。
4. 固定・解除、割付解除、課題表示、計画比較、承認、配台表の開始・完了を確認すること。
5. 既存タスクのID・状態・実績が保持され、旧2テーブルなしでPython仮データとSQL仮データを登録できること。

メモリDBによる40件のテストで、既存CRUD、マスタ編集の反映、自動計算、手動配置・検証、タスク・割付・実績の保持、未生成工程の検出、両方式の仮データ登録を確認した。SQL仮データはINSERT文をSQLiteで実行して登録内容を確認したもので、SQL Server固有の作成・移行SQLの実行確認は別途必要。

## 変更ファイル

バックエンドルートからの相対パス。

- `app/services/task_conditions.py`：条件を組み立てる共通処理を追加。
- `app/services/order_service.py`：タスク本体だけを生成する方式へ変更。
- `app/models/transactions.py`、`app/models/__init__.py`：旧2モデル・関連付け・未使用の関係種別定数を削除。
- `app/engine/snapshot.py`：最新条件を計算へ渡し、未生成工程を検出。
- `app/routers/orders.py`：読取応答を組み立て、旧2テーブルの汎用APIを削除。
- `DataBase/query/create_database_sqlserver.sql`、`DataBase/query/schema_sqlserver.sql`、`DataBase/query/seed_demo_sqlserver.sql`：新規作成・仮データを新構成へ変更。
- `DataBase/query/remove_task_condition_tables_sqlserver.sql`：既存DB用の移行SQLを追加。
- `DataBase/setup_database.py`、`app/services/demo_seed.py`：新構成の説明・初期登録を整合。
- `tests/test_task_conditions.py`：最新条件の反映と既存機能の保持を検証。
- `README.md`、`docs/SYSTEM_OVERVIEW.md`、`docs/TASK_CONDITIONS.md`：保存先・API・移行・確認手順を更新。

フロントエンドルートからの相対パス。

- `src/app/services/master-reference.service.ts`：削除前確認から廃止APIを除去。
- `src/app/interfaces/master-editor.interface.ts`：廃止APIの型を削除。
- `src/app/interfaces/order.interface.ts`：保存しない候補・FS関係の定義とコメントを更新。
- `src/app/services/api.service.ts`：条件の取得方法の説明を更新。
- `src/app/components/main/orders/orders.component.ts`：準備時間を含む所要時間の表示を修正。
- `src/app/components/main/orders/forms/order-form.component.ts`：数量変更後に再生成不要となった案内を修正。
- `docs/PRODUCT_PROCESSES.md`：現在の条件参照とDB移行の説明を更新。
