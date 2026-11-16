<!-- 作業者の通常稼働時間・例外休日・スキルマップの画面、API、既存機能の保持と確認結果を説明する資料。 -->

# 作業者の設定画面（2026-11-16）

## 変更内容と操作

変更前は、作業者名・備考の編集だけが画面から利用でき、通常勤務・例外休日・スキルはテーブルと仮データの登録までだった。
変更後は、サイドバーの「マスタ」→「作業者」で、対象行の「設定」を選び、次の3項目を登録・編集できる。
本人の名前・備考の編集と削除は既存どおり利用できる。

| 表示項目 | 入力・操作 |
| --- | --- |
| 通常稼働時間 | 曜日・開始時刻・終了時刻・勤務名を登録・編集・削除。同じ曜日の午前・午後は別々に登録 |
| 例外休日 | 開始日時・終了日時・備考を登録・編集・削除。全日・時間単位・複数日の休日に対応 |
| スキルマップ | 製品・工程ごとに、担当可能・1日の生産上限・備考を編集して保存 |

作業者の切替や設定項目の切替は、既存の同画面内の編集切替と同じ規則を使う。
保存中の切替を止め、他画面へ移動するときの未保存確認を維持する。
スキルの行は作業者・工程の追加時に全工程分を自動生成するため、新規登録・削除ボタンは表示しない。
担当可能を有効にして保存することで、その工程を担当するスキルを登録する。
担当を解除するときは行を削除せず、担当可能を無効にする。

## DB定義と開発用DBの再作成

作業者の例外休日は`M_WorkerCalendarExceptions.WorkerID`で本人へ直接関連付ける。
同テーブルの旧`WorkerCalendarsID`と勤務行への外部キーを削除し、`M_Workers.WorkerID`への外部キーへ変更する。
通常勤務の主キー`M_WorkerCalendars.WorkerCalendarsID`は勤務1行の識別番号として維持する。
例外休日の日時・備考・監査列と、その他の作業者関連テーブルの定義は維持する。

通常勤務が未登録でも例外休日を登録できる。最後の勤務行も削除でき、例外休日の所属・日時・備考・監査情報はそのまま保持する。
作業者本人の論理削除では、勤務・例外休日・スキルの関連行を保持する。
勤務を再登録した場合は、本人に保持されている例外休日を新しい通常勤務へ適用する。

開発用DBは作り直す前提で、`schema_sqlserver.sql`・`seed_demo_sqlserver.sql`とPython仮データを更新した。
DB削除後に`create_database_sqlserver.sql`、`schema_sqlserver.sql`、`seed_demo_sqlserver.sql`の順で実行する。
実DBの削除・作成・SQL実行とExcelの更新は今回行わない。

## 稼働時間の表示と入力条件

- 拠点カレンダーと同じ共通部品で、月曜始まりの週表示、前週・今週・次週、期間指定・再表示を提供する。
- 曜日の保存番号は従来と同じ日曜0～土曜6。時刻・日時は日本時間で入出力する。
- 通常稼働時間は同じ日の終了が開始より後であることを確認し、日またぎ勤務は受け付けない。
- 通常勤務が未登録の曜日・作業者は、作業者の週表示では稼働なしとする。
- 例外休日は通常勤務から差し引く。休日・勤務時間外へ稼働を追加する設定にはしない。
- スキルは同じ拠点の有効な製品の工程だけを対象とし、登録済みの本人・工程の組合せは変更しない。
- 1日の生産上限は正の数量・小数第3位まで。未設定は追加の上限なしとする。
- 勤務名は50文字以内、例外休日とスキルの備考は500文字以内。
- 削除済みの作業者や拠点への新しい設定保存、不正入力・重複するスキル登録を拒否する。

この作業で追加するのは設定保存・稼働表示までであり、作業者設定を計画計算へ組み込む処理は変更しない。
画面にも現在の計画計算へ反映されないことを表示する。

## API

| API | 用途 |
| --- | --- |
| GET /api/v1/worker-calendars?workerId={id} | 本人の通常稼働時間一覧 |
| POST・PATCH・DELETE /api/v1/worker-calendars | 通常稼働時間の登録・部分更新・論理削除。更新・削除時は末尾に勤務行IDを付ける |
| GET /api/v1/worker-calendar-exceptions?workerId={id} | 本人へ直接紐づく例外休日一覧 |
| POST・PATCH・DELETE /api/v1/worker-calendar-exceptions | 例外休日の登録・部分更新・削除。更新・削除時は末尾に例外IDを付ける |
| GET /api/v1/worker-skill-maps?workerId={id} | 本人の有効な製品工程のスキル一覧 |
| POST・PATCH /api/v1/worker-skill-maps | 不足する担当関係の登録・既存スキルの編集。更新時は末尾に担当関係IDを付ける |
| GET /api/v1/workers/{id}/working-time?from=...&to=... | 本人の通常勤務から例外休日を差し引いた日本時間の稼働区間 |

例外休日の登録項目は`workerId`・`startAt`・`endAt`・`remark`。一覧検索と新規登録はどちらも`workerId`を使う。
登録済み例外休日の`workerId`変更は拒否する。旧`workerCalendarsId`を登録先として送信しない。

スキルのDELETEはHTTP 409で拒否し、全工程との担当関係を保持する。
監査列を持たないスキルマップは専用保存処理を使い、既存の列構成を維持する。

## 共通化した処理と既存機能への影響

拠点カレンダーの週表示を`WorkingTimePreviewComponent`へ移し、作業者の週表示にも同じHTML・スタイル・週切替・期間確認を使用する。
拠点の通常勤務が未登録の場合の常時稼働、停止予定、最後の勤務行の削除保護は変更しない。
勤務未登録の拠点へ切り替えたり、作業者のスキルへ切り替えたりしても、週表示の期間を保持する。
通常稼働時間の時刻確認、例外の日時順序確認、製品・工程の選択肢の作成を共通化し、工程切替画面の表示規則も維持する。
マスタ共通部品へ新規登録・削除ボタンの表示指定を追加した。未指定の既存画面は従来どおり表示する。

## 今回の変更ファイル

| 対象 | ファイル | 内容 |
| --- | --- | --- |
| フロントエンド | `src/app/components/main/workers/workers.component.ts` | 設定対象の作業者選択を追加 |
| フロントエンド | `src/app/components/main/workers/worker-settings.component.ts` | 3つの設定画面を新規作成 |
| フロントエンド | `src/app/components/common/calendar/working-time-preview.component.ts` | 週間稼働表示を共通部品として新規作成 |
| フロントエンド | `src/app/components/main/calendars/calendars.component.ts` | 共通の週間表示と入力確認へ接続 |
| フロントエンド | `src/app/components/common/forms/master-editor.component.ts` | 新規・削除操作の表示指定に対応 |
| フロントエンド | `src/app/interfaces/master-editor.interface.ts` | 3APIと操作表示指定を追加 |
| フロントエンド | `src/app/services/master-form.ts` | 時刻・日時順序・工程選択肢の共通処理を追加 |
| フロントエンド | `src/app/components/main/rules/rules.component.ts` | 既存の工程選択肢を共通処理へ接続 |
| フロントエンド | `src/app/services/api.service.ts` | 作業者の週間稼働取得を追加 |
| フロントエンド | `src/app/services/page-hints.ts` | 作業者メニューの案内を更新 |
| フロントエンド | `README.md` | 現行の作業者機能を記載 |
| バックエンド | `app/routers/masters.py` | 作業者設定3APIと週間稼働APIを追加 |
| バックエンド | `app/services/worker_settings_service.py` | 保存・検証・削除保護・週間稼働取得を新規作成 |
| バックエンド | `README.md` | 作業者機能と仕様書の案内を更新 |
| バックエンド | `docs/SYSTEM_OVERVIEW.md` | 画面・API対応と実装範囲を更新 |
| バックエンド | `docs/WORKER_MASTERS.md` | 現行仕様と基本情報追加時の記録を区別 |
| バックエンド | `docs/WORKER_SETTINGS_20261116.md` | 今回の仕様・変更内容・確認結果を新規作成 |

## 確認結果と画面での確認点

- 午前・午後勤務、昼休み、休日、全面停止、複数日の休日、日本時間保存、本人・拠点の分離を確認。
- 稼働時間と例外休日の登録・部分更新・削除、勤務削除時の休日・監査情報保持、勤務未登録時の休日登録と勤務再登録後の適用を確認。
- スキルの担当可否・日上限・備考の保存、誤入力時の既存値保持、担当関係の削除防止を確認。
- ブラウザ操作・ビルド・解析コマンド・Git操作・実DB変更は未実施。

画面では、作業者ごとに設定が切り替わること、保存・削除が週表示へ反映されること、拠点カレンダーの既存表示が保たれていることを確認する。
保存中の切替防止、他画面への移動時の未保存確認、通信失敗時の入力保持・再読込も確認する。

## WorkerIDへの直接関連付けで変更したファイル

| 対象 | ファイル | 更新内容 |
| --- | --- | --- |
| フロントエンド | `src/app/components/main/workers/worker-settings.component.ts` | 休日の検索・保存をworkerIdへ統一。勤務行取得と未登録時の表示制限を削除 |
| フロントエンド | `README.md` | 直接関連付けとDB再作成の説明を追記 |
| バックエンド | `app/models/masters.py` | 例外休日のWorkerCalendarsIDをWorkerIDへ置き換え、M_Workersを直接参照 |
| バックエンド | `app/services/worker_settings_service.py` | 本人から休日を直接取得。参照付け替えと最終勤務削除の制限・専用一覧検索を削除 |
| バックエンド | `app/routers/masters.py` | 休日の一覧を共通のworkerId検索へ変更 |
| バックエンド | `app/services/demo_seed.py` | Python仮データの休日を本人のWorkerIDへ関連付け |
| バックエンド | `DataBase/query/schema_sqlserver.sql` | 例外休日の列と外部キーを更新 |
| バックエンド | `DataBase/query/seed_demo_sqlserver.sql` | 例外休日のINSERTをWorkerIDへ更新 |
| バックエンド | `DataBase/setup_database.py` | 新規作成時の関連付けの説明を更新 |
| バックエンド | `README.md` | 現行の関連付けと作成クエリ更新を説明 |
| バックエンド | `docs/SYSTEM_OVERVIEW.md` | 本人への直接関連付けを明記 |
| バックエンド | `docs/WORKER_MASTERS.md` | 列構成と関連付け・保持する動作を更新 |
| バックエンド | `docs/WORKER_SETTINGS_20261116.md` | 今回の仕様・変更ファイル・確認結果を更新 |
