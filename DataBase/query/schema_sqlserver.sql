-- 製品・工程・実行候補の3階層を含む、新規DB用のテーブル・制約・索引作成SQL。
-- 改名したID・名称と外部キーを統一し、出荷日時は任意入力として保持する。
-- 設備の費用・属性、オーダーとタスクの親ID、節目指定・予定工数の6列は持たない。
-- 曜日勤務の時刻はTIME、有効期間と実作業日はDATEとし、Pythonのモデル定義に合わせる。
-- 工程番号はアプリの保存処理で製品ごとに1からの連番へ整え、重複指定時は順番を交換する。

-- 既存DBを作り直した後、create_database_sqlserver.sql、このSQL、seed_demo_sqlserver.sqlの順で実行する。

USE [TONOPS-SCH];
GO

CREATE TABLE [M_Organizations] (
	[OrganizationID] INTEGER NOT NULL IDENTITY, 
	[OrganizationName] NVARCHAR(100) NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Organizations] PRIMARY KEY ([OrganizationID])
);
GO

CREATE TABLE [M_AttributeDefinitions] (
	[AttributeDefID] INTEGER NOT NULL IDENTITY, 
	[OrganizationID] INTEGER NOT NULL, 
	[EntityType] NVARCHAR(20) NOT NULL, 
	[AttributeKey] NVARCHAR(50) NOT NULL, 
	[Label] NVARCHAR(100) NOT NULL, 
	[DataType] NVARCHAR(20) NOT NULL, 
	[EnumValuesJSON] NVARCHAR(max) NULL, 
	[IsRequired] BIT NOT NULL, 
	[SortOrder] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_AttributeDefinitions] PRIMARY KEY ([AttributeDefID]), 
	CONSTRAINT [UQ_M_AttributeDefinitions_OrganizationID_EntityType_AttributeKey] UNIQUE ([OrganizationID], [EntityType], [AttributeKey]), 
	CONSTRAINT [CK_M_AttributeDefinitions_EntityType] CHECK (EntityType IN ('PRODUCT','RESOURCE','ORDER','TASK')), 
	CONSTRAINT [CK_M_AttributeDefinitions_DataType] CHECK (DataType IN ('TEXT','NUMBER','BOOL','DATE','ENUM')), 
	CONSTRAINT [FK_M_AttributeDefinitions_OrganizationID_M_Organizations] FOREIGN KEY([OrganizationID]) REFERENCES [M_Organizations] ([OrganizationID])
);
GO

CREATE TABLE [M_Locations] (
	[LocationID] INTEGER NOT NULL IDENTITY, 
	[OrganizationID] INTEGER NOT NULL, 
	[LocationName] NVARCHAR(100) NOT NULL, 
	[DefaultCalendarID] INTEGER NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Locations] PRIMARY KEY ([LocationID]), 
	CONSTRAINT [FK_M_Locations_OrganizationID_M_Organizations] FOREIGN KEY([OrganizationID]) REFERENCES [M_Organizations] ([OrganizationID])
);
GO

CREATE TABLE [M_Calendars] (
	[CalendarID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[CalendarName] NVARCHAR(100) NOT NULL, 
	[ParentCalendarID] INTEGER NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Calendars] PRIMARY KEY ([CalendarID]), 
	CONSTRAINT [FK_M_Calendars_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID]), 
	CONSTRAINT [FK_M_Calendars_ParentCalendarID_M_Calendars] FOREIGN KEY([ParentCalendarID]) REFERENCES [M_Calendars] ([CalendarID])
);
GO

CREATE TABLE [M_CalculationSettings] (
	[CalculationSettingID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[CalculationSettingName] NVARCHAR(100) NOT NULL, 
	[TimeUnit] NVARCHAR(10) NOT NULL, 
	[ObjectiveWeightsJSON] NVARCHAR(max) NOT NULL, 
	[TimeLimitSec] INTEGER NOT NULL, 
	[FrozenWindowHours] INTEGER NOT NULL, 
	[IsDefault] BIT NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
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
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Product] PRIMARY KEY ([ProductID]), 
	CONSTRAINT [UQ_M_Product_LocationID_ProductName] UNIQUE ([LocationID], [ProductName]), 
	CONSTRAINT [FK_M_Product_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID])
);
GO

CREATE TABLE [M_ResourceGroups] (
	[ResourceGroupID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[GroupName] NVARCHAR(100) NOT NULL, 
	[SortOrder] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_ResourceGroups] PRIMARY KEY ([ResourceGroupID]), 
	CONSTRAINT [FK_M_ResourceGroups_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID])
);
GO

CREATE TABLE [M_Rules] (
	[RuleID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[RuleTypeKey] NVARCHAR(50) NOT NULL, 
	[RuleName] NVARCHAR(100) NOT NULL, 
	[SelectorJSON] NVARCHAR(max) NOT NULL, 
	[ParamsJSON] NVARCHAR(max) NOT NULL, 
	[IsHard] BIT NOT NULL, 
	[Weight] INTEGER NOT NULL, 
	[ValidFrom] DATE NULL, 
	[ValidTo] DATE NULL, 
	[IsActive] BIT NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_Rules] PRIMARY KEY ([RuleID]), 
	CONSTRAINT [FK_M_Rules_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID])
);
GO

CREATE TABLE [M_CalendarExceptions] (
	[ExceptionID] INTEGER NOT NULL IDENTITY, 
	[CalendarID] INTEGER NOT NULL, 
	[StartAt] DATETIME2 NOT NULL, 
	[EndAt] DATETIME2 NOT NULL, 
	[IsWorking] BIT NOT NULL, 
	[Reason] NVARCHAR(100) NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_CalendarExceptions] PRIMARY KEY ([ExceptionID]), 
	CONSTRAINT [FK_M_CalendarExceptions_CalendarID_M_Calendars] FOREIGN KEY([CalendarID]) REFERENCES [M_Calendars] ([CalendarID]) ON DELETE CASCADE
);
GO

CREATE TABLE [M_CalendarPatterns] (
	[PatternID] INTEGER NOT NULL IDENTITY, 
	[CalendarID] INTEGER NOT NULL, 
	[DayOfWeek] SMALLINT NOT NULL, 
	[StartTime] TIME NOT NULL, 
	[EndTime] TIME NOT NULL, 
	[ShiftName] NVARCHAR(50) NULL, 
	[ValidFrom] DATE NULL, 
	[ValidTo] DATE NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_CalendarPatterns] PRIMARY KEY ([PatternID]), 
	CONSTRAINT [CK_M_CalendarPatterns_DayOfWeek] CHECK (DayOfWeek BETWEEN 1 AND 7), 
	CONSTRAINT [FK_M_CalendarPatterns_CalendarID_M_Calendars] FOREIGN KEY([CalendarID]) REFERENCES [M_Calendars] ([CalendarID]) ON DELETE CASCADE
);
GO

CREATE TABLE [M_ProductSwitchTimes] (
	[ProductSwitchTimeID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[ProductSwitchTimeName] NVARCHAR(100) NOT NULL, 
	[AttributeKey] NVARCHAR(50) NOT NULL, 
	[ResourceGroupID] INTEGER NULL, 
	[DefaultMinutes] INTEGER NOT NULL, 
	[IsActive] BIT NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_ProductSwitchTimes] PRIMARY KEY ([ProductSwitchTimeID]), 
	CONSTRAINT [FK_M_ProductSwitchTimes_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID]), 
	CONSTRAINT [FK_M_ProductSwitchTimes_ResourceGroupID_M_ResourceGroups] FOREIGN KEY([ResourceGroupID]) REFERENCES [M_ResourceGroups] ([ResourceGroupID])
);
GO

CREATE TABLE [M_ProductProcesses] (
	[ProductProcessID] INTEGER NOT NULL IDENTITY, 
	[ProductID] INTEGER NOT NULL, 
	[SequenceNumber] INTEGER NOT NULL, 
	[ProcessName] NVARCHAR(100) NOT NULL, 
	[MinLagAfterMin] INTEGER NOT NULL, 
	[MaxLagAfterMin] INTEGER NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_ProductProcesses] PRIMARY KEY ([ProductProcessID]), 
	CONSTRAINT [UQ_M_ProductProcesses_ProductID_SequenceNumber] UNIQUE ([ProductID], [SequenceNumber]), 
	CONSTRAINT [FK_M_ProductProcesses_ProductID_M_Product] FOREIGN KEY([ProductID]) REFERENCES [M_Product] ([ProductID]) ON DELETE CASCADE
);
GO

CREATE TABLE [M_Resources] (
	[ResourceID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[ResourceGroupID] INTEGER NULL, 
	[ResourceName] NVARCHAR(100) NOT NULL, 
	[ResourceType] NVARCHAR(20) NOT NULL, 
	[Capacity] NUMERIC(9, 2) NOT NULL, 
	[DailyCapacityHours] NUMERIC(5, 2) NULL, 
	[CalendarID] INTEGER NULL, 
	[SortOrder] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Resources] PRIMARY KEY ([ResourceID]), 
	CONSTRAINT [CK_M_Resources_ResourceType] CHECK (ResourceType IN ('MACHINE','PERSON','TEAM','ROOM','OTHER')), 
	CONSTRAINT [FK_M_Resources_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID]), 
	CONSTRAINT [FK_M_Resources_ResourceGroupID_M_ResourceGroups] FOREIGN KEY([ResourceGroupID]) REFERENCES [M_ResourceGroups] ([ResourceGroupID]), 
	CONSTRAINT [FK_M_Resources_CalendarID_M_Calendars] FOREIGN KEY([CalendarID]) REFERENCES [M_Calendars] ([CalendarID])
);
GO

CREATE TABLE [T_Orders] (
	[OrderID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[WBSNumber] NVARCHAR(30) NOT NULL, 
	[OrderName] NVARCHAR(200) NOT NULL, 
	[OrderType] NVARCHAR(20) NOT NULL, 
	[ProductID] INTEGER NULL, 
	[Quantity] NUMERIC(18, 3) NULL, 
	[CustomerName] NVARCHAR(100) NULL, 
	[ReleaseAt] DATETIME2 NULL, 
	[DeadLine] DATETIME2 NULL,
	[ShippingDate] DATETIME2(7) NULL, 
	[Priority] INTEGER NOT NULL, 
	[Status] NVARCHAR(20) NOT NULL, 
	[PlanOwner] NVARCHAR(20) NOT NULL, 
	[AttributesJSON] NVARCHAR(max) NULL, 
	[Remarks] NVARCHAR(500) NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_T_Orders] PRIMARY KEY ([OrderID]), 
	CONSTRAINT [UQ_T_Orders_LocationID_WBSNumber] UNIQUE ([LocationID], [WBSNumber]), 
	CONSTRAINT [CK_T_Orders_OrderType] CHECK (OrderType IN ('ORDER','PROJECT')), 
	CONSTRAINT [CK_T_Orders_Status] CHECK (Status IN ('OPEN','PLANNED','IN_PROGRESS','DONE','CANCELLED')), 
	CONSTRAINT [CK_T_Orders_PlanOwner] CHECK (PlanOwner IN ('SCHEDULER','EXTERNAL')), 
	CONSTRAINT [FK_T_Orders_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID]), 
	CONSTRAINT [FK_T_Orders_ProductID_M_Product] FOREIGN KEY([ProductID]) REFERENCES [M_Product] ([ProductID])
);
GO

CREATE TABLE [T_Plans] (
	[PlanID] INTEGER NOT NULL IDENTITY, 
	[LocationID] INTEGER NOT NULL, 
	[PlanName] NVARCHAR(100) NOT NULL, 
	[Status] NVARCHAR(20) NOT NULL, 
	[HorizonStart] DATETIME2 NOT NULL, 
	[HorizonEnd] DATETIME2 NOT NULL, 
	[CalculationSettingID] INTEGER NOT NULL, 
	[BasePlanID] INTEGER NULL, 
	[SupersededAt] DATETIME2 NULL, 
	[ApprovedAt] DATETIME2 NULL, 
	[ApprovedBy] NVARCHAR(254) NULL, 
	[Remarks] NVARCHAR(500) NULL, 
	[RowVer] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_Plans] PRIMARY KEY ([PlanID]), 
	CONSTRAINT [UQ_T_Plans_LocationID_PlanName] UNIQUE ([LocationID], [PlanName]), 
	CONSTRAINT [CK_T_Plans_Status] CHECK (Status IN ('DRAFT','MASTER','SUPERSEDED','DISCARDED','ARCHIVED')), 
	CONSTRAINT [FK_T_Plans_LocationID_M_Locations] FOREIGN KEY([LocationID]) REFERENCES [M_Locations] ([LocationID]), 
	CONSTRAINT [FK_T_Plans_CalculationSettingID_M_CalculationSettings] FOREIGN KEY([CalculationSettingID]) REFERENCES [M_CalculationSettings] ([CalculationSettingID]), 
	CONSTRAINT [FK_T_Plans_BasePlanID_T_Plans] FOREIGN KEY([BasePlanID]) REFERENCES [T_Plans] ([PlanID])
);
GO

CREATE TABLE [M_ProductSwitchRules] (
	[ProductSwitchRuleID] INTEGER NOT NULL IDENTITY, 
	[ProductSwitchTimeID] INTEGER NOT NULL, 
	[FromValue] NVARCHAR(50) NOT NULL, 
	[ToValue] NVARCHAR(50) NOT NULL, 
	[SetupMinutes] INTEGER NOT NULL, 
	[IsForbidden] BIT NOT NULL, 
	[Cost] NUMERIC(12, 2) NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_ProductSwitchRules] PRIMARY KEY ([ProductSwitchRuleID]), 
	CONSTRAINT [UQ_M_ProductSwitchRules_ProductSwitchTimeID_FromValue_ToValue] UNIQUE ([ProductSwitchTimeID], [FromValue], [ToValue]), 
	CONSTRAINT [FK_M_ProductSwitchRules_ProductSwitchTimeID_M_ProductSwitchTimes] FOREIGN KEY([ProductSwitchTimeID]) REFERENCES [M_ProductSwitchTimes] ([ProductSwitchTimeID]) ON DELETE CASCADE
);
GO

CREATE TABLE [M_ProductProcessResources] (
	[ProductProcessResourceID] INTEGER NOT NULL IDENTITY, 
	[ProductProcessID] INTEGER NOT NULL, 
	[ResourceID] INTEGER NULL, 
	[ResourceGroupID] INTEGER NULL, 
	[SetupMinutes] INTEGER NOT NULL, 
	[FixedMinutes] INTEGER NOT NULL, 
	[MinutesPerUnit] NUMERIC(12, 4) NOT NULL, 
	[Priority] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_ProductProcessResources] PRIMARY KEY ([ProductProcessResourceID]), 
	CONSTRAINT [CK_M_ProductProcessResources_ResourceOrGroup] CHECK ((ResourceID IS NULL AND ResourceGroupID IS NOT NULL) OR (ResourceID IS NOT NULL AND ResourceGroupID IS NULL)), 
	CONSTRAINT [FK_M_ProductProcessResources_ProductProcessID_M_ProductProcesses] FOREIGN KEY([ProductProcessID]) REFERENCES [M_ProductProcesses] ([ProductProcessID]) ON DELETE CASCADE, 
	CONSTRAINT [FK_M_ProductProcessResources_ResourceID_M_Resources] FOREIGN KEY([ResourceID]) REFERENCES [M_Resources] ([ResourceID]), 
	CONSTRAINT [FK_M_ProductProcessResources_ResourceGroupID_M_ResourceGroups] FOREIGN KEY([ResourceGroupID]) REFERENCES [M_ResourceGroups] ([ResourceGroupID])
);
GO

CREATE TABLE [T_PlanKpis] (
	[PlanID] INTEGER NOT NULL, 
	[KpiKey] NVARCHAR(50) NOT NULL, 
	[KpiValue] NUMERIC(18, 4) NOT NULL, 
	CONSTRAINT [PK_T_PlanKpis] PRIMARY KEY ([PlanID], [KpiKey]), 
	CONSTRAINT [FK_T_PlanKpis_PlanID_T_Plans] FOREIGN KEY([PlanID]) REFERENCES [T_Plans] ([PlanID]) ON DELETE CASCADE
);
GO

CREATE TABLE [T_SolverRunResult] (
	[RunID] INTEGER NOT NULL IDENTITY, 
	[PlanID] INTEGER NOT NULL, 
	[Status] NVARCHAR(20) NOT NULL, 
	[Scope] NVARCHAR(20) NOT NULL, 
	[RequestedBy] NVARCHAR(254) NOT NULL, 
	[RequestedAt] DATETIME2 NOT NULL, 
	[StartedAt] DATETIME2 NULL, 
	[FinishedAt] DATETIME2 NULL, 
	[TimeLimitSec] INTEGER NOT NULL, 
	[SolverStatus] NVARCHAR(20) NULL, 
	[ObjectiveValue] FLOAT NULL, 
	[BestBound] FLOAT NULL, 
	[TaskCount] INTEGER NULL, 
	[ProgressJSON] NVARCHAR(max) NULL, 
	[ErrorMessage] NTEXT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_SolverRunResult] PRIMARY KEY ([RunID]), 
	CONSTRAINT [CK_T_SolverRunResult_Status] CHECK (Status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')), 
	CONSTRAINT [CK_T_SolverRunResult_Scope] CHECK (Scope IN ('FULL','REPAIR')), 
	CONSTRAINT [FK_T_SolverRunResult_PlanID_T_Plans] FOREIGN KEY([PlanID]) REFERENCES [T_Plans] ([PlanID])
);
GO

CREATE INDEX [IX_T_SolverRunResult_Status_RequestedAt] ON [T_SolverRunResult] ([Status], [RequestedAt]);
GO

CREATE TABLE [T_Tasks] (
	[TaskID] INTEGER NOT NULL IDENTITY, 
	[OrderID] INTEGER NOT NULL, 
	[ProductProcessID] INTEGER NULL, 
	[TaskNo] NVARCHAR(30) NOT NULL, 
	[TaskName] NVARCHAR(200) NOT NULL, 
	[Sequence] INTEGER NOT NULL, 
	[IsSummary] BIT NOT NULL, 
	[EarliestStartAt] DATETIME2 NULL, 
	[DeadlineAt] DATETIME2 NULL, 
	[Status] NVARCHAR(20) NOT NULL, 
	[ProgressPct] NUMERIC(5, 2) NOT NULL, 
	[AttributesJSON] NVARCHAR(max) NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_Tasks] PRIMARY KEY ([TaskID]), 
	CONSTRAINT [UQ_T_Tasks_OrderID_TaskNo] UNIQUE ([OrderID], [TaskNo]), 
	CONSTRAINT [CK_T_Tasks_Status] CHECK (Status IN ('NOT_STARTED','IN_PROGRESS','DONE','CANCELLED')), 
	CONSTRAINT [FK_T_Tasks_OrderID_T_Orders] FOREIGN KEY([OrderID]) REFERENCES [T_Orders] ([OrderID]), 
	CONSTRAINT [FK_T_Tasks_ProductProcessID_M_ProductProcesses] FOREIGN KEY([ProductProcessID]) REFERENCES [M_ProductProcesses] ([ProductProcessID])
);
GO

CREATE TABLE [T_WorkActuals] (
	[WorkActualID] BIGINT NOT NULL IDENTITY, 
	[TaskID] INTEGER NOT NULL, 
	[ResourceID] INTEGER NULL, 
	[StartAt] DATETIME2 NULL, 
	[EndAt] DATETIME2 NULL, 
	[WorkDate] DATE NULL, 
	[WorkHours] NUMERIC(9, 2) NULL, 
	[Quantity] NUMERIC(18, 3) NULL, 
	[Status] NVARCHAR(20) NOT NULL, 
	[Source] NVARCHAR(10) NOT NULL, 
	[ExternalKey] NVARCHAR(100) NULL, 
	[Remarks] NVARCHAR(500) NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_WorkActuals] PRIMARY KEY ([WorkActualID]), 
	CONSTRAINT [CK_T_WorkActuals_Status] CHECK (Status IN ('IN_PROGRESS','DONE','SUSPENDED')), 
	CONSTRAINT [CK_T_WorkActuals_Source] CHECK (Source IN ('MANUAL','PMS','IMPORT')), 
	CONSTRAINT [FK_T_WorkActuals_TaskID_T_Tasks] FOREIGN KEY([TaskID]) REFERENCES [T_Tasks] ([TaskID]), 
	CONSTRAINT [FK_T_WorkActuals_ResourceID_M_Resources] FOREIGN KEY([ResourceID]) REFERENCES [M_Resources] ([ResourceID])
);
GO

CREATE TABLE [T_PlanAssignments] (
	[AssignmentID] BIGINT NOT NULL IDENTITY, 
	[PlanID] INTEGER NOT NULL, 
	[TaskID] INTEGER NOT NULL, 
	[ResourceID] INTEGER NOT NULL, 
	[StartAt] DATETIME2 NOT NULL, 
	[EndAt] DATETIME2 NOT NULL, 
	[SetupMinutes] INTEGER NOT NULL, 
	[Units] NUMERIC(5, 2) NOT NULL, 
	[IsLocked] BIT NOT NULL, 
	[Source] NVARCHAR(10) NOT NULL, 
	[RowVer] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_PlanAssignments] PRIMARY KEY ([AssignmentID]), 
	CONSTRAINT [UQ_T_PlanAssignments_PlanID_TaskID] UNIQUE ([PlanID], [TaskID]), 
	CONSTRAINT [CK_T_PlanAssignments_EndAfterStart] CHECK (EndAt > StartAt), 
	CONSTRAINT [CK_T_PlanAssignments_Source] CHECK (Source IN ('SOLVER','MANUAL','IMPORT')), 
	CONSTRAINT [FK_T_PlanAssignments_PlanID_T_Plans] FOREIGN KEY([PlanID]) REFERENCES [T_Plans] ([PlanID]) ON DELETE CASCADE, 
	CONSTRAINT [FK_T_PlanAssignments_TaskID_T_Tasks] FOREIGN KEY([TaskID]) REFERENCES [T_Tasks] ([TaskID]), 
	CONSTRAINT [FK_T_PlanAssignments_ResourceID_M_Resources] FOREIGN KEY([ResourceID]) REFERENCES [M_Resources] ([ResourceID])
);
GO

CREATE INDEX [IX_T_PlanAssignments_PlanID_ResourceID_StartAt] ON [T_PlanAssignments] ([PlanID], [ResourceID], [StartAt]);
GO

CREATE TABLE [T_PlanViolations] (
	[ViolationID] BIGINT NOT NULL IDENTITY, 
	[PlanID] INTEGER NOT NULL, 
	[RuleID] INTEGER NULL, 
	[TaskID] INTEGER NULL, 
	[Severity] NVARCHAR(10) NOT NULL, 
	[Penalty] NUMERIC(18, 2) NULL, 
	[Message] NVARCHAR(500) NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_PlanViolations] PRIMARY KEY ([ViolationID]), 
	CONSTRAINT [CK_T_PlanViolations_Severity] CHECK (Severity IN ('HARD','SOFT','INFO')), 
	CONSTRAINT [FK_T_PlanViolations_PlanID_T_Plans] FOREIGN KEY([PlanID]) REFERENCES [T_Plans] ([PlanID]) ON DELETE CASCADE, 
	CONSTRAINT [FK_T_PlanViolations_RuleID_M_Rules] FOREIGN KEY([RuleID]) REFERENCES [M_Rules] ([RuleID]), 
	CONSTRAINT [FK_T_PlanViolations_TaskID_T_Tasks] FOREIGN KEY([TaskID]) REFERENCES [T_Tasks] ([TaskID])
);
GO

CREATE TABLE [T_TaskDependencies] (
	[DependencyID] INTEGER NOT NULL IDENTITY, 
	[PredecessorTaskID] INTEGER NOT NULL, 
	[SuccessorTaskID] INTEGER NOT NULL, 
	[DependencyType] NVARCHAR(2) NOT NULL, 
	[LagMin] INTEGER NOT NULL, 
	[MaxLagMin] INTEGER NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_TaskDependencies] PRIMARY KEY ([DependencyID]), 
	CONSTRAINT [UQ_T_TaskDependencies_PredecessorTaskID_SuccessorTaskID] UNIQUE ([PredecessorTaskID], [SuccessorTaskID]), 
	CONSTRAINT [CK_T_TaskDependencies_DependencyType] CHECK (DependencyType IN ('FS','SS','FF','SF')), 
	CONSTRAINT [FK_T_TaskDependencies_PredecessorTaskID_T_Tasks] FOREIGN KEY([PredecessorTaskID]) REFERENCES [T_Tasks] ([TaskID]), 
	CONSTRAINT [FK_T_TaskDependencies_SuccessorTaskID_T_Tasks] FOREIGN KEY([SuccessorTaskID]) REFERENCES [T_Tasks] ([TaskID])
);
GO

CREATE TABLE [T_TaskResourceOptions] (
	[OptionID] INTEGER NOT NULL IDENTITY, 
	[TaskID] INTEGER NOT NULL, 
	[ResourceID] INTEGER NULL, 
	[ResourceGroupID] INTEGER NULL, 
	[DurationMin] INTEGER NOT NULL, 
	[SetupMinutes] INTEGER NOT NULL, 
	[Units] NUMERIC(5, 2) NOT NULL, 
	[Priority] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_TaskResourceOptions] PRIMARY KEY ([OptionID]), 
	CONSTRAINT [CK_T_TaskResourceOptions_ResourceOrGroup] CHECK ((ResourceID IS NULL AND ResourceGroupID IS NOT NULL) OR (ResourceID IS NOT NULL AND ResourceGroupID IS NULL)), 
	CONSTRAINT [FK_T_TaskResourceOptions_TaskID_T_Tasks] FOREIGN KEY([TaskID]) REFERENCES [T_Tasks] ([TaskID]) ON DELETE CASCADE, 
	CONSTRAINT [FK_T_TaskResourceOptions_ResourceID_M_Resources] FOREIGN KEY([ResourceID]) REFERENCES [M_Resources] ([ResourceID]), 
	CONSTRAINT [FK_T_TaskResourceOptions_ResourceGroupID_M_ResourceGroups] FOREIGN KEY([ResourceGroupID]) REFERENCES [M_ResourceGroups] ([ResourceGroupID])
);
GO

ALTER TABLE [M_Locations] ADD CONSTRAINT [FK_M_Locations_DefaultCalendarID_M_Calendars] FOREIGN KEY([DefaultCalendarID]) REFERENCES [M_Calendars] ([CalendarID]);
GO
