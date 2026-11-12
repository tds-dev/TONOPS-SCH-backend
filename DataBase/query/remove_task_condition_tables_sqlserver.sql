-- 既存DBから設備候補・前後関係の複製テーブルだけを削除する移行SQL。
-- 更新後のアプリと併せて適用する。タスク本体・計画・割付・実績・製品マスタは保持する。
-- 旧テーブルの個別変更は引き継がず、以後は現在の製品工程と数量を基準に計算する。
USE [TONOPS-SCH];
GO
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;
    -- 製品工程へ紐づかない作業は、移行前に生成元を設定する必要がある。
    IF EXISTS (
        SELECT 1
        FROM [T_Tasks] AS t
        INNER JOIN [T_Orders] AS o ON o.[OrderID] = t.[OrderID]
        LEFT JOIN [M_ProductProcesses] AS p ON p.[ProductProcessID] = t.[ProductProcessID]
        WHERE t.[IsSummary] = 0 AND t.[Status] NOT IN ('DONE', 'CANCELLED')
          AND o.[DeleteFlag] = 0 AND o.[Status] NOT IN ('DONE', 'CANCELLED')
          AND o.[PlanOwner] = 'SCHEDULER'
          AND (p.[ProductProcessID] IS NULL OR p.[ProductID] <> o.[ProductID] OR o.[ProductID] IS NULL)
    )
        THROW 50001, N'計算対象のタスクを、所属オーダーの製品工程へ紐づけてから移行してください。', 1;

    -- 再実行時も、存在する旧テーブルだけを削除する。
    IF OBJECT_ID(N'dbo.T_TaskDependencies', N'U') IS NOT NULL
        DROP TABLE [dbo].[T_TaskDependencies];
    IF OBJECT_ID(N'dbo.T_TaskResourceOptions', N'U') IS NOT NULL
        DROP TABLE [dbo].[T_TaskResourceOptions];
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
