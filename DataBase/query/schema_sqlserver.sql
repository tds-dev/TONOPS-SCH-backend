-- 2026-11-20: T_Orders.WorkerIDを廃止し、監査列のないT_OrderWorkersで複数の担当者を保持する。
-- 段取り替えは切替前後の製品工程IDを参照し、NULLは任意の工程を表す。
-- 作業者の例外休日はWorkerIDで本人へ直接関連付け、通常稼働時間とは独立して保持する。
-- 2026-11-16: 拠点のCalendarIDを廃止し、週間勤務・停止予定をLocationIDで直接関連付ける。
-- 2026-11-13: 旧属性定義・ルールを廃止。曜日制限は製品工程へ保存。
-- 製品・工程・実行候補の3階層を含む、新規DB用のテーブル・制約・索引作成SQL。
-- 改名したID・名称と外部キーを統一し、出荷日時は任意入力として保持する。
-- オーダーは種別・計画の管理元・属性、タスクは作業番号・集約指定・進捗率・属性の列を持たない。
-- 設備の費用・属性、オーダーとタスクの親ID、節目指定・予定工数の6列は持たない。
-- 組織と勤務パターンは廃止し、拠点ごとの曜日・時間帯をM_Calendarsへ直接保存する。
-- 曜日勤務の時刻はTIME、休日・停止の例外日時は日本時間のDATETIME2とする。
-- 工程番号はアプリの保存処理で製品ごとに1からの連番へ整え、重複指定時は順番を交換する。
-- タスクの設備候補・前後関係は製品工程から利用時に組み立て、専用の複製テーブルは作成しない。

-- DBを削除した後、create_database_sqlserver.sql、このSQL、seed_demo_sqlserver.sqlの順で再作成する。

-- 2026-11-12: 設備は所属拠点の勤務を共有し、計算時間上限を廃止。作業中実績はEndAt・StatusともNULL。
USE [TONOPS-SCH];
GO

CREATE TABLE [M_Locations] (
	[LocationID] INTEGER NOT NULL IDENTITY, 
	[LocationName] NVARCHAR(100) NOT NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Locations] PRIMARY KEY ([LocationID])
);
GO

CREATE TABLE [M_Calendars] (
	[CalendarID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[DayOfWeek] SMALLINT NOT NULL, 
	[StartTime] DATETIME NOT NULL, 
	[EndTime] DATETIME NOT NULL, 
	[WorkName] NVARCHAR(50) NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Calendars] PRIMARY KEY ([CalendarID]), 
	CONSTRAINT [CK_M_Calendars_DayOfWeek] CHECK (DayOfWeek BETWEEN 0 AND 6), 
	CONSTRAINT [CK_M_Calendars_EndAfterStart] CHECK (EndTime > StartTime), 
	CONSTRAINT [FK_M_Calendars_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID])
);
GO

CREATE TABLE [M_ResourceGroups] (
	[ResourceGroupID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[GroupName] NVARCHAR(100) NOT NULL, 
	[SortOrder] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_ResourceGroups] PRIMARY KEY ([ResourceGroupID]), 
	CONSTRAINT [FK_M_ResourceGroups_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID])
);
GO

CREATE TABLE [M_CalculationSettings] (
	[CalculationSettingID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[CalculationSettingName] NVARCHAR(100) NOT NULL, 
	[TimeUnit] NVARCHAR(10) NOT NULL, 
	[ObjectiveWeightsJSON] NVARCHAR(max) NOT NULL, 
	[FrozenWindowHours] INTEGER NOT NULL, 
	[IsDefault] BIT NOT NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_CalculationSettings] PRIMARY KEY ([CalculationSettingID]), 
	CONSTRAINT [CK_M_CalculationSettings_TimeUnit] CHECK (TimeUnit IN ('MINUTE','DAY')), 
	CONSTRAINT [FK_M_CalculationSettings_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID])
);
GO

CREATE TABLE [M_Product] (
	[ProductID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[ProductName] NVARCHAR(100) NOT NULL, 
	[ProductCode] NVARCHAR(100) NULL,
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Product] PRIMARY KEY ([ProductID]), 
	CONSTRAINT [UQ_M_Product_LocationID_ProductName] UNIQUE ([LocationID], [ProductName]), 
	CONSTRAINT [FK_M_Product_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID])
);
GO

CREATE TABLE [M_Workers] (
	[WorkerID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[WorkerName] NVARCHAR(100) NOT NULL, 
	[Remarks] NVARCHAR(500) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Workers] PRIMARY KEY ([WorkerID]), 
	CONSTRAINT [FK_M_Workers_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID])
);
GO

CREATE TABLE [M_CalendarExceptions] (
	[ExceptionID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[StartAt] DATETIME2(7) NOT NULL, 
	[EndAt] DATETIME2(7) NOT NULL, 
	[Reason] NVARCHAR(100) NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_CalendarExceptions] PRIMARY KEY ([ExceptionID]), 
	CONSTRAINT [CK_M_CalendarExceptions_EndAfterStart] CHECK (EndAt > StartAt), 
	CONSTRAINT [FK_M_CalendarExceptions_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID])
);
GO

CREATE TABLE [M_Resources] (
	[ResourceID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[ResourceGroupID] INTEGER NULL, 
	[ResourceName] NVARCHAR(100) NOT NULL, 
	[Capacity] NUMERIC(9, 2) NOT NULL, 
	[DailyCapacityHours] NUMERIC(5, 2) NULL, 
	[SortOrder] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Resources] PRIMARY KEY ([ResourceID]), 
	CONSTRAINT [FK_M_Resources_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID]), 
	CONSTRAINT [FK_M_Resources_ResourceGroupID_M_ResourceGroups] FOREIGN KEY([ResourceGroupID]) REFERENCES [M_ResourceGroups] ([ResourceGroupID])
);
GO

CREATE TABLE [M_ProductSwitchTimes] (
	[ProductSwitchTimeID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[ProductSwitchTimeName] NVARCHAR(100) NOT NULL, 
	[ResourceID] INTEGER NULL,
	[ResourceGroupID] INTEGER NULL, 
	[DefaultMinutes] INTEGER NOT NULL, 
	[IsActive] BIT NOT NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_ProductSwitchTimes] PRIMARY KEY ([ProductSwitchTimeID]), 
	CONSTRAINT [CK_M_ProductSwitchTimes_ResourceScope] CHECK (ResourceID IS NULL OR ResourceGroupID IS NULL),
	CONSTRAINT [FK_M_ProductSwitchTimes_ResourceID_M_Resources] FOREIGN KEY([ResourceID]) REFERENCES [M_Resources] ([ResourceID]),
	CONSTRAINT [FK_M_ProductSwitchTimes_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID]), 
	CONSTRAINT [FK_M_ProductSwitchTimes_ResourceGroupID_M_ResourceGroups] FOREIGN KEY([ResourceGroupID]) REFERENCES [M_ResourceGroups] ([ResourceGroupID])
);
GO

CREATE TABLE [M_ProductProcesses] (
	[ProductProcessID] INTEGER NOT NULL IDENTITY, 
	[ProductID] INTEGER NOT NULL, 
	[SequenceNumber] INTEGER NOT NULL, 
	[ProcessName] NVARCHAR(100) NOT NULL, 
	-- 作業時間は工程共通。設備候補には複製しない。
	[SetupMinutes] INTEGER NULL, 
	[FixedMinutes] INTEGER NULL, 
	[ProcessingMinutes] NUMERIC(12, 4) NOT NULL, 
	[MinLagAfterMin] INTEGER NOT NULL, 
	[MaxLagAfterMin] INTEGER NULL, 
	[AllowedWeekdaysJSON] NVARCHAR(max) NOT NULL DEFAULT '[0,1,2,3,4,5,6]', 
	[WeekdayRestrictionEnabled] BIT NOT NULL DEFAULT 1, 
	[WeekdayRestrictionStartAt] DATETIME2(7) NULL, 
	[WeekdayRestrictionEndAt] DATETIME2(7) NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_ProductProcesses] PRIMARY KEY ([ProductProcessID]), 
	CONSTRAINT [UQ_M_ProductProcesses_ProductID_SequenceNumber] UNIQUE ([ProductID], [SequenceNumber]), 
	CONSTRAINT [CK_M_ProductProcesses_WeekdayRestrictionPeriod] CHECK (WeekdayRestrictionStartAt IS NULL OR WeekdayRestrictionEndAt IS NULL OR WeekdayRestrictionStartAt <= WeekdayRestrictionEndAt), 
	CONSTRAINT [FK_M_ProductProcesses_ProductID_M_Product] FOREIGN KEY([ProductID]) REFERENCES [M_Product] ([ProductID]) ON DELETE CASCADE
);
GO

CREATE TABLE [M_WorkerCalendars] (
	[WorkerCalendarsID] INTEGER NOT NULL IDENTITY, 
	[WorkerID] INTEGER NOT NULL, 
	[DayOfWeek] SMALLINT NOT NULL, 
	[StartTime] DATETIME NOT NULL, 
	[EndTime] DATETIME NOT NULL, 
	[WorkName] NVARCHAR(50) NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_WorkerCalendars] PRIMARY KEY ([WorkerCalendarsID]), 
	CONSTRAINT [CK_M_WorkerCalendars_DayOfWeek] CHECK (DayOfWeek BETWEEN 0 AND 6), 
	CONSTRAINT [CK_M_WorkerCalendars_EndAfterStart] CHECK (EndTime > StartTime), 
	CONSTRAINT [FK_M_WorkerCalendars_WorkerID_M_Workers] FOREIGN KEY([WorkerID]) REFERENCES [M_Workers] ([WorkerID])
);
GO

CREATE TABLE [T_Orders] (
	[OrderID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[WBSNumber] NVARCHAR(30) NOT NULL, 
	[OrderName] NVARCHAR(200) NOT NULL, 
	[ProductID] INTEGER NULL, 
	[Quantity] NUMERIC(18, 3) NULL, 
	[CustomerName] NVARCHAR(100) NULL, 
	[ReleaseAt] DATETIME2(7) NULL, 
	[DeadLine] DATETIME2(7) NULL, 
	[ShippingDate] DATETIME2(7) NULL, 
	[Priority] INTEGER NOT NULL, 
	[Status] NVARCHAR(20) NOT NULL, 
	[Remarks] NVARCHAR(500) NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_T_Orders] PRIMARY KEY ([OrderID]), 
	CONSTRAINT [UQ_T_Orders_LocationID_WBSNumber] UNIQUE ([LocationID], [WBSNumber]), 
	CONSTRAINT [CK_T_Orders_Status] CHECK (Status IN ('OPEN','PLANNED','IN_PROGRESS','DONE','CANCELLED')), 
	CONSTRAINT [FK_T_Orders_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID]), 
	CONSTRAINT [FK_T_Orders_ProductID_M_Product] FOREIGN KEY([ProductID]) REFERENCES [M_Product] ([ProductID])
);
GO

-- オーダーの担当者は複数行で保持する。監査列を持たず、同じ担当者の二重登録を防ぐ。
CREATE TABLE [T_OrderWorkers] (
    [OrderWorkerID] INTEGER NOT NULL IDENTITY,
    [OrderID] INTEGER NOT NULL,
    [WorkerID] INTEGER NOT NULL,
    CONSTRAINT [PK_T_OrderWorkers] PRIMARY KEY ([OrderWorkerID]),
    CONSTRAINT [UQ_T_OrderWorkers_OrderID_WorkerID] UNIQUE ([OrderID], [WorkerID]),
    CONSTRAINT [FK_T_OrderWorkers_OrderID_T_Orders] FOREIGN KEY([OrderID]) REFERENCES [T_Orders] ([OrderID]),
    CONSTRAINT [FK_T_OrderWorkers_WorkerID_M_Workers] FOREIGN KEY([WorkerID]) REFERENCES [M_Workers] ([WorkerID])
);
GO

CREATE TABLE [T_Plans] (
	[PlanID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[PlanName] NVARCHAR(100) NOT NULL, 
	[Status] NVARCHAR(20) NOT NULL, 
	[StartAt] DATETIME2(7) NOT NULL, 
	[EndAt] DATETIME2(7) NOT NULL, 
	[CalculationSettingID] INTEGER NOT NULL, 
	[BasePlanID] INTEGER NULL, 
	-- 直接コピーした元の計画。通常の新規作成ではNULL。
	[CopiedFromPlanID] INTEGER NULL,
	[SupersededAt] DATETIME2(7) NULL, 
	[ApprovedAt] DATETIME2(7) NULL, 
	[ApprovedBy] NVARCHAR(254) NULL, 
	[Remarks] NVARCHAR(500) NULL, 
	[RowVer] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_Plans] PRIMARY KEY ([PlanID]), 
	CONSTRAINT [UQ_T_Plans_LocationID_PlanName] UNIQUE ([LocationID], [PlanName]), 
	CONSTRAINT [CK_T_Plans_Status] CHECK (Status IN ('DRAFT','MASTER','SUPERSEDED','DISCARDED','ARCHIVED')), 
	CONSTRAINT [FK_T_Plans_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID]), 
	CONSTRAINT [FK_T_Plans_CalculationSettingID_M_CalculationSettings] FOREIGN KEY([CalculationSettingID]) REFERENCES [M_CalculationSettings] ([CalculationSettingID]), 
	CONSTRAINT [FK_T_Plans_BasePlanID_T_Plans] FOREIGN KEY([BasePlanID]) REFERENCES [T_Plans] ([PlanID]),
	CONSTRAINT [FK_T_Plans_CopiedFromPlanID_T_Plans] FOREIGN KEY([CopiedFromPlanID]) REFERENCES [T_Plans] ([PlanID])
);
GO

CREATE TABLE [M_ProductSwitchRules] (
	[ProductSwitchRuleID] INTEGER NOT NULL IDENTITY, 
	[ProductSwitchTimeID] INTEGER NOT NULL, 
	[FromProductProcessID] INTEGER NULL, 
	[ToProductProcessID] INTEGER NULL, 
	[SetupMinutes] INTEGER NOT NULL, 
	[IsForbidden] BIT NOT NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_ProductSwitchRules] PRIMARY KEY ([ProductSwitchRuleID]), 
	CONSTRAINT [UQ_M_ProductSwitchRules_ProductSwitchTimeID_FromProductProcessID_ToProductProcessID] UNIQUE ([ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID]), 
	CONSTRAINT [FK_M_ProductSwitchRules_ProductSwitchTimeID_M_ProductSwitchTimes] FOREIGN KEY([ProductSwitchTimeID]) REFERENCES [M_ProductSwitchTimes] ([ProductSwitchTimeID]) ON DELETE CASCADE, 
	CONSTRAINT [FK_M_ProductSwitchRules_FromProductProcessID_M_ProductProcesses] FOREIGN KEY([FromProductProcessID]) REFERENCES [M_ProductProcesses] ([ProductProcessID]), 
	CONSTRAINT [FK_M_ProductSwitchRules_ToProductProcessID_M_ProductProcesses] FOREIGN KEY([ToProductProcessID]) REFERENCES [M_ProductProcesses] ([ProductProcessID])
);
GO

CREATE TABLE [M_ProductProcessResources] (
	[ProductProcessResourceID] INTEGER NOT NULL IDENTITY, 
	[ProductProcessID] INTEGER NOT NULL, 
	[ResourceID] INTEGER NULL, 
	[ResourceGroupID] INTEGER NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_ProductProcessResources] PRIMARY KEY ([ProductProcessResourceID]), 
	CONSTRAINT [CK_M_ProductProcessResources_ResourceOrGroup] CHECK ((ResourceID IS NULL AND ResourceGroupID IS NOT NULL) OR (ResourceID IS NOT NULL AND ResourceGroupID IS NULL)), 
	CONSTRAINT [FK_M_ProductProcessResources_ProductProcessID_M_ProductProcesses] FOREIGN KEY([ProductProcessID]) REFERENCES [M_ProductProcesses] ([ProductProcessID]) ON DELETE CASCADE, 
	CONSTRAINT [FK_M_ProductProcessResources_ResourceID_M_Resources] FOREIGN KEY([ResourceID]) REFERENCES [M_Resources] ([ResourceID]), 
	CONSTRAINT [FK_M_ProductProcessResources_ResourceGroupID_M_ResourceGroups] FOREIGN KEY([ResourceGroupID]) REFERENCES [M_ResourceGroups] ([ResourceGroupID])
);
GO

CREATE TABLE [M_WorkerSkillMap] (
	[WorkerSkillMapID] INTEGER NOT NULL IDENTITY, 
	[WorkerID] INTEGER NOT NULL, 
	[ProductProcessID] INTEGER NOT NULL, 
	[CanExecute] BIT NOT NULL, 
	[MaxDailyQuantity] NUMERIC(18, 3) NULL, 
	[Remarks] NVARCHAR(500) NULL, 
	CONSTRAINT [PK_M_WorkerSkillMap] PRIMARY KEY ([WorkerSkillMapID]), 
	CONSTRAINT [UQ_M_WorkerSkillMap_WorkerID_ProductProcessID] UNIQUE ([WorkerID], [ProductProcessID]), 
	CONSTRAINT [CK_M_WorkerSkillMap_MaxDailyQuantity] CHECK (MaxDailyQuantity IS NULL OR MaxDailyQuantity > 0), 
	CONSTRAINT [FK_M_WorkerSkillMap_WorkerID_M_Workers] FOREIGN KEY([WorkerID]) REFERENCES [M_Workers] ([WorkerID]), 
	CONSTRAINT [FK_M_WorkerSkillMap_ProductProcessID_M_ProductProcesses] FOREIGN KEY([ProductProcessID]) REFERENCES [M_ProductProcesses] ([ProductProcessID]) ON DELETE CASCADE
);
GO

CREATE TABLE [M_WorkerCalendarExceptions] (
	[ExceptionID] INTEGER NOT NULL IDENTITY, 
	[WorkerID] INTEGER NOT NULL, 
	[StartAt] DATETIME2(7) NOT NULL, 
	[EndAt] DATETIME2(7) NOT NULL, 
	[Remark] NVARCHAR(500) NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_WorkerCalendarExceptions] PRIMARY KEY ([ExceptionID]), 
	CONSTRAINT [CK_M_WorkerCalendarExceptions_EndAfterStart] CHECK (EndAt > StartAt), 
	CONSTRAINT [FK_M_WorkerCalendarExceptions_WorkerID_M_Workers] FOREIGN KEY([WorkerID]) REFERENCES [M_Workers] ([WorkerID])
);
GO

CREATE TABLE [T_Tasks] (
	[TaskID] INTEGER NOT NULL IDENTITY, 
	[OrderID] INTEGER NOT NULL, 
	[ProductProcessID] INTEGER NULL, 
	[TaskName] NVARCHAR(200) NOT NULL, 
	[Sequence] INTEGER NOT NULL, 
	[EarliestStartAt] DATETIME2(7) NULL, 
	[DeadlineAt] DATETIME2(7) NULL, 
	[Status] NVARCHAR(20) NOT NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_Tasks] PRIMARY KEY ([TaskID]), 
	CONSTRAINT [CK_T_Tasks_Status] CHECK (Status IN ('NOT_STARTED','IN_PROGRESS','DONE','CANCELLED')), 
	CONSTRAINT [FK_T_Tasks_OrderID_T_Orders] FOREIGN KEY([OrderID]) REFERENCES [T_Orders] ([OrderID]), 
	CONSTRAINT [FK_T_Tasks_ProductProcessID_M_ProductProcesses] FOREIGN KEY([ProductProcessID]) REFERENCES [M_ProductProcesses] ([ProductProcessID])
);
GO

CREATE TABLE [T_SolverRunResult] (
	[RunID] INTEGER NOT NULL IDENTITY, 
	[PlanID] INTEGER NOT NULL, 
	[Status] NVARCHAR(20) NOT NULL, 
	[Scope] NVARCHAR(20) NOT NULL, 
	[RequestedBy] NVARCHAR(254) NOT NULL, 
	[RequestedAt] DATETIME2(7) NOT NULL, 
	[StartAt] DATETIME2(7) NULL, 
	[EndAt] DATETIME2(7) NULL, 
	[SolverStatus] NVARCHAR(20) NULL, 
	[ObjectiveValue] FLOAT NULL, 
	[BestBound] FLOAT NULL, 
	[TaskCount] INTEGER NULL, 
	[ProgressJSON] NVARCHAR(max) NULL, 
	[ErrorMessage] NTEXT NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_SolverRunResult] PRIMARY KEY ([RunID]), 
	CONSTRAINT [CK_T_SolverRunResult_Status] CHECK (Status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')), 
	CONSTRAINT [CK_T_SolverRunResult_Scope] CHECK (Scope IN ('FULL','REPAIR')), 
	CONSTRAINT [FK_T_SolverRunResult_PlanID_T_Plans] FOREIGN KEY([PlanID]) REFERENCES [T_Plans] ([PlanID])
);
GO

CREATE INDEX [IX_T_SolverRunResult_Status_RequestedAt] ON [T_SolverRunResult] ([Status], [RequestedAt]);
GO

CREATE TABLE [T_PlanKpis] (
	[PlanID] INTEGER NOT NULL, 
	[KpiKey] NVARCHAR(50) NOT NULL, 
	[KpiValue] NUMERIC(18, 4) NOT NULL, 
	CONSTRAINT [PK_T_PlanKpis] PRIMARY KEY ([PlanID], [KpiKey]), 
	CONSTRAINT [FK_T_PlanKpis_PlanID_T_Plans] FOREIGN KEY([PlanID]) REFERENCES [T_Plans] ([PlanID]) ON DELETE CASCADE
);
GO

CREATE TABLE [T_PlanAssignments] (
	[AssignmentID] BIGINT NOT NULL IDENTITY, 
	[PlanID] INTEGER NOT NULL, 
	[TaskID] INTEGER NOT NULL, 
	[ResourceID] INTEGER NOT NULL, 
	[WorkerID] INTEGER NOT NULL,
	[StartAt] DATETIME2(7) NOT NULL, 
	[EndAt] DATETIME2(7) NOT NULL, 
	[SetupMinutes] INTEGER NOT NULL, 
	[Units] NUMERIC(5, 2) NOT NULL, 
	[IsLocked] BIT NOT NULL, 
	[Source] NVARCHAR(10) NOT NULL, 
	[RowVer] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_PlanAssignments] PRIMARY KEY ([AssignmentID]), 
	CONSTRAINT [UQ_T_PlanAssignments_PlanID_TaskID] UNIQUE ([PlanID], [TaskID]), 
	CONSTRAINT [CK_T_PlanAssignments_EndAfterStart] CHECK (EndAt > StartAt), 
	CONSTRAINT [CK_T_PlanAssignments_Source] CHECK (Source IN ('SOLVER','MANUAL','IMPORT')), 
	CONSTRAINT [FK_T_PlanAssignments_PlanID_T_Plans] FOREIGN KEY([PlanID]) REFERENCES [T_Plans] ([PlanID]) ON DELETE CASCADE, 
	CONSTRAINT [FK_T_PlanAssignments_TaskID_T_Tasks] FOREIGN KEY([TaskID]) REFERENCES [T_Tasks] ([TaskID]), 
	CONSTRAINT [FK_T_PlanAssignments_ResourceID_M_Resources] FOREIGN KEY([ResourceID]) REFERENCES [M_Resources] ([ResourceID]),
	CONSTRAINT [FK_T_PlanAssignments_WorkerID_M_Workers] FOREIGN KEY([WorkerID]) REFERENCES [M_Workers] ([WorkerID])
);
GO

CREATE INDEX [IX_T_PlanAssignments_PlanID_ResourceID_StartAt] ON [T_PlanAssignments] ([PlanID], [ResourceID], [StartAt]);
GO

CREATE TABLE [T_PlanViolations] (
	[ViolationID] BIGINT NOT NULL IDENTITY, 
	[PlanID] INTEGER NOT NULL, 
	[TaskID] INTEGER NULL, 
	[Severity] NVARCHAR(10) NOT NULL, 
	[Penalty] NUMERIC(18, 2) NULL, 
	[Message] NVARCHAR(500) NOT NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_PlanViolations] PRIMARY KEY ([ViolationID]), 
	CONSTRAINT [CK_T_PlanViolations_Severity] CHECK (Severity IN ('HARD','SOFT','INFO')), 
	CONSTRAINT [FK_T_PlanViolations_PlanID_T_Plans] FOREIGN KEY([PlanID]) REFERENCES [T_Plans] ([PlanID]) ON DELETE CASCADE, 
	CONSTRAINT [FK_T_PlanViolations_TaskID_T_Tasks] FOREIGN KEY([TaskID]) REFERENCES [T_Tasks] ([TaskID])
);
GO

CREATE TABLE [T_WorkActuals] (
	[WorkActualID] BIGINT NOT NULL IDENTITY, 
	[TaskID] INTEGER NOT NULL, 
	[ResourceID] INTEGER NULL, 
	[StartAt] DATETIME2(7) NULL, 
	[EndAt] DATETIME2(7) NULL, 
	[Quantity] NUMERIC(18, 3) NULL, 
	[Status] NVARCHAR(20) NULL, 
	[Remarks] NVARCHAR(500) NULL, 
	[CreatedAt] DATETIME2(7) NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2(7) NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_WorkActuals] PRIMARY KEY ([WorkActualID]), 
	CONSTRAINT [CK_T_WorkActuals_Status] CHECK (Status IN ('DONE','SUSPENDED')), 
	CONSTRAINT [CK_T_WorkActuals_EndStatus] CHECK ((EndAt IS NULL AND Status IS NULL) OR (EndAt IS NOT NULL AND Status IS NOT NULL)), 
	CONSTRAINT [CK_T_WorkActuals_EndAfterStart] CHECK (EndAt IS NULL OR (StartAt IS NOT NULL AND EndAt >= StartAt)), 
	CONSTRAINT [FK_T_WorkActuals_TaskID_T_Tasks] FOREIGN KEY([TaskID]) REFERENCES [T_Tasks] ([TaskID]), 
	CONSTRAINT [FK_T_WorkActuals_ResourceID_M_Resources] FOREIGN KEY([ResourceID]) REFERENCES [M_Resources] ([ResourceID])
);
GO

