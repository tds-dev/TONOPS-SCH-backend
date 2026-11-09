-- 既存のT_Plansへ、拠点内で計画名を重複させない制約を追加するSQL。
-- SSMSで対象DBを確認して手動適用する。既存データの変更・削除は行わない。
-- 新規DBはschema_sqlserver.sqlまたは現在のモデル定義を使用する。
USE [TONOPS-SCH];
GO

SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    -- 名称未設定の既存データは勝手に命名せず、対象を表示して適用を停止する。
    IF EXISTS (SELECT 1 FROM [dbo].[T_Plans] WHERE LTRIM(RTRIM([PlanName])) = N'')
    BEGIN
        SELECT [PlanID], [LocationID], [PlanName]
        FROM [dbo].[T_Plans]
        WHERE LTRIM(RTRIM([PlanName])) = N'';
        THROW 50001, N'計画名が空欄の計画があります。名前を設定してから再実行してください。', 1;
    END;

    -- 前後の空白を除いて同名になる計画も確認し、状態にかかわらず重複を検出する。
    IF EXISTS (
        SELECT 1 FROM [dbo].[T_Plans]
        GROUP BY [LocationID], LTRIM(RTRIM([PlanName]))
        HAVING COUNT(*) > 1
    )
    BEGIN
        SELECT [PlanID], [LocationID], [PlanName]
        FROM (
            SELECT [PlanID], [LocationID], [PlanName],
                COUNT(*) OVER (PARTITION BY [LocationID], LTRIM(RTRIM([PlanName]))) AS [DuplicateCount]
            FROM [dbo].[T_Plans]
        ) AS [DuplicatePlans]
        WHERE [DuplicateCount] > 1
        ORDER BY [LocationID], [PlanName], [PlanID];
        THROW 50002, N'同じ拠点に同名の計画があります。名前の重複を解消してから再実行してください。', 1;
    END;

    -- 適用済みの制約を再追加しない。
    IF NOT EXISTS (
        SELECT 1 FROM sys.key_constraints
        WHERE [parent_object_id] = OBJECT_ID(N'[dbo].[T_Plans]')
          AND [name] = N'UQ_T_Plans_LocationID_PlanName'
    )
    BEGIN
        ALTER TABLE [dbo].[T_Plans]
        ADD CONSTRAINT [UQ_T_Plans_LocationID_PlanName] UNIQUE ([LocationID], [PlanName]);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
