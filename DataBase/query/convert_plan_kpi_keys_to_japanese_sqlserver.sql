-- 既存のT_PlanKpisに保存された英語キーだけを日本語へ変換する。
-- 対象DBを選択し、バックエンド・計算ワーカーを停止した状態で手動実行する。
-- 同一計画に新旧両方の行がある場合は、日本語側の評価値を残す。
-- 再実行しても日本語へ変換済みの行は変更しない。
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    -- アプリのLEGACY_KPI_KEYSと同じ7指標の対応表。
    DECLARE @KpiKeyMap TABLE (
        OldKey NVARCHAR(50) NOT NULL PRIMARY KEY,
        NewKey NVARCHAR(50) NOT NULL UNIQUE
    );
    INSERT INTO @KpiKeyMap (OldKey, NewKey) VALUES
        (N'late_orders', N'納期遅れ'),
        (N'total_lateness_min', N'遅れ時間の合計'),
        (N'setup_min', N'段取り時間'),
        (N'makespan_min', N'最終完了'),
        (N'utilisation_pct', N'平均負荷率'),
        (N'scheduled_tasks', N'割付済みタスク'),
        (N'unscheduled_tasks', N'未割付タスク');

    -- 日本語行が既にある場合は旧行だけを除き、主キーの重複を防ぐ。
    DELETE old
    FROM [T_PlanKpis] AS old
    INNER JOIN @KpiKeyMap AS mapping ON mapping.OldKey = old.KpiKey
    WHERE EXISTS (
        SELECT 1 FROM [T_PlanKpis] AS currentKpi
        WHERE currentKpi.PlanID = old.PlanID AND currentKpi.KpiKey = mapping.NewKey
    );

    -- 指標の値・所属計画はそのままに、保存キーだけを変更する。
    UPDATE kpi
    SET KpiKey = mapping.NewKey
    FROM [T_PlanKpis] AS kpi
    INNER JOIN @KpiKeyMap AS mapping ON mapping.OldKey = kpi.KpiKey;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
