<!-- 製品工程IDによる段取り替えのDB・API・計算・画面と、DB作成時の注意点を説明する資料。 -->
# 製品工程の組合せによる段取り替え

2026-11-13更新。モデル・DB作成SQL・フロントエンドの`docs/DB.xlsx`は23テーブル・255カラム。

## 変更前と変更後

| 対象 | 変更前 | 変更後 |
|---|---|---|
| 判定の基準 | 作業のAttributesJSONに入れた分類文字列 | 作業のProductProcessID |
| M_ProductSwitchTimes | AttributeKeyで判定項目を指定 | AttributeKeyを削除。拠点・設備グループ・既定時間・有効状態は保持 |
| M_ProductSwitchRules | FromValue・ToValueの文字列 | FromProductProcessID・ToProductProcessIDの工程参照 |
| 任意指定 | `*` | NULL |
| 通常生成した作業 | 別途属性を設定する必要があった | 生成元工程IDからそのまま判定できる |
| ボードの既定色分け | 段取り替え設定の属性 | 製品ID。明示的なcolorByによる旧属性表示は保持 |

新しいテーブルは追加しない。独立した段取り替え用2テーブルから、製品工程へ外部キーで関連付ける。

## DB定義

`M_ProductSwitchRules`の`FromProductProcessID`・`ToProductProcessID`はINT・NULL可で、どちらも`M_ProductProcesses.ProductProcessID`を参照する。NULLは「任意の工程」。参照中の工程の物理削除は拒否する。

同じ設定内で`ProductSwitchTimeID + FromProductProcessID + ToProductProcessID`を一意にする。SQL Serverの一意制約に加え、APIでもNULLを含む重複を確認する。別拠点の工程・設備グループ、負の時間、不正な有効状態は登録しない。

一つの設備へ複数の有効設定を重ねない。全設備指定は同じ拠点の有効なグループ別設定とも重複扱いにする。無効な設定は切替候補として保持できる。

## 条件の優先順位

1. 切替前後の工程を両方指定した明細。
2. 切替前だけを指定した明細。
3. 切替後だけを指定した明細。
4. 両方NULLの明細。
5. 設定のDefaultMinutes。

同じ工程IDどうしは、個別の明細があればその条件、なければ0分・禁止なしとする。最初の作業には切替前の作業がないため切替時間を付けない。生成元工程が不明な既存作業にも任意指定を誤適用しない。

切替時間と禁止順序は、同じ単一能力設備で直前・直後となる作業間に適用する。製品内の次工程との待ち時間であるMinLagAfterMin・MaxLagAfterMinとは、対象の関係が異なる。

## APIと画面

- `/product-switch-times`：属性名欄を削除し、対象設備グループ・既定時間・有効状態を登録・更新する。
- `/product-switch-rules`：前後を「製品名／順番：工程名」から選ぶ。「すべての工程」（旧表示「任意の工程」）はNULLで保存する。個別条件の優先順位と、同一工程には個別明細だけを適用する動作は維持する。
- 明細の「設定内容」で「切替時間を設定」または「この順序を禁止」を選ぶ。禁止時は時間入力を隠し、一覧の時間は「—」とする。再度時間設定へ戻せるよう、既存の時間は保持する。
- 前後とも「すべての工程」にした順序禁止は画面とAPIで拒否する。片側だけの全工程指定、両側全工程への時間設定、個別の禁止設定は維持する。既存DBにこの禁止設定がある場合は計算条件の読込時にも修正を案内する。
- `/product-processes?locationId=...`：製品の所属拠点で工程候補を絞る。削除済み製品の工程は候補から除外する。
- 画面・APIのURLは既存のものを維持する。

明細登録・更新の例：

```json
{
  "productSwitchTimeId": 1,
  "fromProductProcessId": 1,
  "toProductProcessId": 10,
  "setupMinutes": 30,
  "isForbidden": false
}
```

親設定を削除すると所属明細を連動削除する。工程・作業・割付・実績を連動削除する構造にはしない。

## 計算と既存機能

`engine/snapshot.py`が作業の工程IDと切替明細を取得する。`PChangeover.lookup`で任意指定の優先順位を共用し、`Problem.changeover_for`で設備に適用する設定の検索を共用する。自動計算・手動編集後の切替時間再計算・禁止順序検証に同じ工程IDを渡す。

工程順・曜日制限・最小最大待ち時間・設備候補・固定準備時間・計画コピー・承認・作業状態・実績参照は維持する。T_Tasks.AttributesJSONは削除せず、旧データ・API応答・明示した属性での色分けのために保持する。段取り替えの判定には使わない。

## DB作成と仮データ

新規の空DBでは`create_database_sqlserver.sql`→`schema_sqlserver.sql`→`seed_demo_sqlserver.sql`の順で実行する。Pythonの初期設定も同じ定義と仮設定を作る。

以前の分類間6ルールは、対応する「こねる」工程IDの22組へ展開する。食事パン→菓子パンは10分、食事パン・菓子パン→ナッツ入りは15分、ナッツ入り→他分類は20分という仮設定を維持する。製品工程を先に挿入し、参照先ができてから明細を登録する。

DB構成を変更した場合は、DBを削除してからPython初期設定または上記の手動SQLでDB・テーブル・仮データを再作成する。

今回、実DBへの接続・変更は行っていない。

## 確認内容

画面では工程参照、すべての工程の指定、重複・別拠点指定の拒否、編集取消、削除保護を確認する。自動計算と手動編集で切替時間・禁止順序が反映され、計画ボードの製品色分けが保たれることも確認する。

確認結果：Python構文確認が成功。SQL Server向けBIT条件式の生成、モデル・SQL・Excelの23テーブル・255カラム、SQL版・Python版の22件の切替明細の一致も確認した。

ビルド・コードレビュー用コマンド・Git操作・外部通信を伴うコマンドは実行しない。ブラウザーの実画面とSQL ServerへのDDL適用は未確認。

## 変更ファイル

各リポジトリのルートからの相対パス。

### TONOPS-SCH-backend

- `README.md`
- `docs/SYSTEM_OVERVIEW.md`
- `docs/DB_SCHEMA_UPDATE_20261113.md`
- `DataBase/setup_database.py`
- `DataBase/query/seed_demo_sqlserver.sql`
- `DataBase/query/schema_sqlserver.sql`
- `DataBase/query/create_database_sqlserver.sql`
- `app/services/product_process_service.py`
- `app/services/demo_seed.py`
- `app/services/board_service.py`
- `app/models/masters.py`
- `app/models/transactions.py`
- `app/routers/masters.py`
- `app/engine/snapshot.py`
- `app/engine/problem.py`
- `app/engine/model_builder.py`
- `app/engine/evaluate.py`
- `app/engine/edit.py`
- `app/services/product_switch_service.py`（追加）
- `docs/PRODUCT_PROCESS_SWITCHES.md`（追加）

### TONOPS-SCH-frontend

- `README.md`
- `src/app/services/page-hints.ts`
- `src/app/services/master-reference.service.ts`
- `src/app/interfaces/master-editor.interface.ts`
- `docs/PRODUCT_PROCESSES.md`
- `docs/DB.xlsx`
- `src/app/components/main/rules/rules.component.ts`
- `src/app/components/main/products/products.component.ts`
- `src/app/components/common/forms/master-editor.component.ts`
