-- 既存の M_ProductProcesses テーブルへ MaxHolidaysAfter 列（初期値 NULL）と CHECK 制約を追加する。
-- 工程終了直後に続く休日（拠点休日・担当作業者の休み含む）の許容上限日数を保持する。
-- 既に列・制約が存在する場合はスキップするため、再実行してもエラーにならない。
USE [TONOPS-SCH];
GO

IF COL_LENGTH(N'dbo.M_ProductProcesses', N'MaxHolidaysAfter') IS NULL
BEGIN
    ALTER TABLE [dbo].[M_ProductProcesses]
        ADD [MaxHolidaysAfter] INTEGER NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_M_ProductProcesses_MaxHolidaysAfter'
      AND parent_object_id = OBJECT_ID(N'dbo.M_ProductProcesses')
)
BEGIN
    ALTER TABLE [dbo].[M_ProductProcesses]
        ADD CONSTRAINT [CK_M_ProductProcesses_MaxHolidaysAfter]
        CHECK ([MaxHolidaysAfter] IS NULL OR [MaxHolidaysAfter] >= 0);
END;
GO
