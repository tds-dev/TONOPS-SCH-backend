<!-- Order系のDB作成・初期データSQLの出力内容と利用順序を説明する資料。 -->
# DB作成・初期データSQL（2026-10-30）

プログラムにはDB作成、テーブル作成、デモデータ登録の処理がある。
テーブルと挿入先はモデル定義から生成するため、現在はT_Orders、OrderID、OrderNo等を使う。
種別の定義名もRESOURCE_TYPE・ORDER_TYPEへ統一し、DB列・挿入先はResourceType・OrderTypeを使う。
DB名自体は引き続きTONOPS-SCHとする。

## 手動実行用の生成SQL

| 順序 | ファイル | 内容 |
| --- | --- | --- |
| 1 | `db/create_database_sqlserver.sql` | TONOPS-SCHが存在しない場合だけ作成する |
| 2 | `db/schema_sqlserver.sql` | 26テーブル、制約、インデックスを作成する |
| 3 | `db/seed_demo_sqlserver.sql` | オーダー7件、タスク21件、関連マスタ等の145行を挿入する |

今回行ったのはSQLファイルの出力のみ。SQL Serverでの作成・挿入は実行していない。
これらは新規構築用であり、既存テーブルの名称変更や既存データの移行用ではない。
既存のDBを残す場合、これらのCREATE/INSERTではなく、別途名称変更と保存値の移行が必要。

## 生成元

- `scripts/create_database.py`: 接続先のDBがなければ作成する既存処理。テーブル名は扱わない。
- `scripts/create_schema.py`: モデルから実DBにテーブルを作成する既存処理。
- `scripts/seed_demo.py`、`app/services/demo_seed.py`: モデルから実DBへ初期データを登録する既存処理。
- `scripts/export_ddl.py`: SQL Server向けのDB・テーブル作成文をファイルへ出力する。
- `scripts/export_seed_sql.py`: 既存のデモ登録処理をメモリSQLiteで実行し、INSERT文をファイルへ出力する。実DBには接続しない。

## 再出力

以下はファイルを出力するコマンドであり、実DBへのSQL実行は行わない。

```text
python -m scripts.export_ddl
python -m scripts.export_seed_sql --base-date 2026-10-30
```

DB名を変えて出力する場合は、両方に同じ`--database-name`を指定する。
基準日を省略したデモデータは、実行時点の翌日06:00（日本時間）以降の予定になる。
今回出力したデモデータは2026-10-30を基準とし、開始可能日時は2026-10-31 06:00（日本時間）。

## 既存処理への影響と確認

実DBへ接続する既存の作成・登録処理と、画面・APIの業務処理は変更していない。
デモデータの定義を複製せずに再利用し、プログラムとSQLのデータ内容がずれないようにする。
拠点とカレンダーの相互参照は、テーブル作成後のALTER文とデータ挿入後のUPDATE文で設定する。
生成SQLはID値、工程順序、タスク候補、属性のJSONを維持する。

生成したINSERT文を別のメモリDBへ読み込み、外部キーを有効にした状態で7件のオーダーと21件のタスクを再現した。
SQLの生成を含む23件の関連テストと、変更したPythonの構文確認が通過した。
SQL Server固有のCREATE DATABASE、GO、IDENTITY_INSERT等の実行は未確認。
生成済みSQLの変更前の内容は表示せず、一時フォルダーへ退避してから再出力した。

## KINDSからTYPEへの変更対象

定義名はRESOURCE_KINDSからRESOURCE_TYPE、ORDER_KINDSからORDER_TYPEへ変更した。
対応するモデル、API、画面、初期データ、テストも同じType名を参照する。
種別の保存値や表示文言は変更していない。既存DBを利用する場合は、別途列名と制約の名称変更が必要。

- バックエンド: `app/models/masters.py`、`app/models/transactions.py`、`app/services/demo_seed.py`、`app/services/board_service.py`
- フロントエンド: `src/app/interfaces/master.interface.ts`、`src/app/interfaces/order.interface.ts`、`src/app/interfaces/board.interface.ts`、`src/app/components/main/resources/resources.component.ts`、`src/app/components/main/orders/orders.component.ts`
- テスト: `tests/test_api_phase1.py`、`tests/test_orders.py`、`tests/test_export_sql.py`
- 出力SQL: `db/create_database_sqlserver.sql`、`db/schema_sqlserver.sql`、`db/seed_demo_sqlserver.sql`
