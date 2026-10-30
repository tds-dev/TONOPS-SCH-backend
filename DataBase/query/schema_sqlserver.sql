-- DataBase/queryに配置した、SSMSで手動実行するテーブル作成SQL。
-- 新規DB向けの作成SQL。既存DBの名称変更用SQLではない。

USE [TONOPS-SCH];
GO

CREATE TABLE [M_Organizations] (
	[OrganizationID] INTEGER NOT NULL IDENTITY, 
	[OrganizationCode] NVARCHAR(30) NOT NULL, 
	[OrganizationName] NVARCHAR(100) NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Organizations] PRIMARY KEY ([OrganizationID]), 
	CONSTRAINT [UQ_M_Organizations_OrganizationCode] UNIQUE ([OrganizationCode])
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
	CONSTRAINT [CK_M_AttributeDefinitions_EntityType] CHECK (EntityType IN ('ITEM','RESOURCE','ORDER','TASK')), 
	CONSTRAINT [CK_M_AttributeDefinitions_DataType] CHECK (DataType IN ('TEXT','NUMBER','BOOL','DATE','ENUM')), 
	CONSTRAINT [FK_M_AttributeDefinitions_OrganizationID_M_Organizations] FOREIGN KEY([OrganizationID]) REFERENCES [M_Organizations] ([OrganizationID])
);
GO

CREATE TABLE [M_Sites] (
	[SiteID] INTEGER NOT NULL IDENTITY, 
	[OrganizationID] INTEGER NOT NULL, 
	[SiteCode] NVARCHAR(30) NOT NULL, 
	[SiteName] NVARCHAR(100) NOT NULL, 
	[TimeZone] NVARCHAR(50) NOT NULL, 
	[DefaultCalendarID] INTEGER NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Sites] PRIMARY KEY ([SiteID]), 
	CONSTRAINT [UQ_M_Sites_OrganizationID_SiteCode] UNIQUE ([OrganizationID], [SiteCode]), 
	CONSTRAINT [FK_M_Sites_OrganizationID_M_Organizations] FOREIGN KEY([OrganizationID]) REFERENCES [M_Organizations] ([OrganizationID])
);
GO

CREATE TABLE [M_Calendars] (
	[CalendarID] INTEGER NOT NULL IDENTITY, 
	[SiteID] INTEGER NOT NULL, 
	[CalendarCode] NVARCHAR(30) NOT NULL, 
	[CalendarName] NVARCHAR(100) NOT NULL, 
	[ParentCalendarID] INTEGER NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Calendars] PRIMARY KEY ([CalendarID]), 
	CONSTRAINT [UQ_M_Calendars_SiteID_CalendarCode] UNIQUE ([SiteID], [CalendarCode]), 
	CONSTRAINT [FK_M_Calendars_SiteID_M_Sites] FOREIGN KEY([SiteID]) REFERENCES [M_Sites] ([SiteID]), 
	CONSTRAINT [FK_M_Calendars_ParentCalendarID_M_Calendars] FOREIGN KEY([ParentCalendarID]) REFERENCES [M_Calendars] ([CalendarID])
);
GO

CREATE TABLE [M_Items] (
	[ItemID] INTEGER NOT NULL IDENTITY, 
	[SiteID] INTEGER NOT NULL, 
	[ItemCode] NVARCHAR(30) NOT NULL, 
	[ItemName] NVARCHAR(100) NOT NULL, 
	[Unit] NVARCHAR(10) NULL, 
	[AttributesJSON] NVARCHAR(max) NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Items] PRIMARY KEY ([ItemID]), 
	CONSTRAINT [UQ_M_Items_SiteID_ItemCode] UNIQUE ([SiteID], [ItemCode]), 
	CONSTRAINT [FK_M_Items_SiteID_M_Sites] FOREIGN KEY([SiteID]) REFERENCES [M_Sites] ([SiteID])
);
GO

CREATE TABLE [M_PlanProfiles] (
	[ProfileID] INTEGER NOT NULL IDENTITY, 
	[SiteID] INTEGER NOT NULL, 
	[ProfileName] NVARCHAR(100) NOT NULL, 
	[TimeUnit] NVARCHAR(10) NOT NULL, 
	[ObjectiveWeightsJSON] NVARCHAR(max) NOT NULL, 
	[TimeLimitSec] INTEGER NOT NULL, 
	[FrozenWindowHours] INTEGER NOT NULL, 
	[IsDefault] BIT NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_PlanProfiles] PRIMARY KEY ([ProfileID]), 
	CONSTRAINT [CK_M_PlanProfiles_TimeUnit] CHECK (TimeUnit IN ('MINUTE','DAY')), 
	CONSTRAINT [FK_M_PlanProfiles_SiteID_M_Sites] FOREIGN KEY([SiteID]) REFERENCES [M_Sites] ([SiteID])
);
GO

CREATE TABLE [M_ResourceGroups] (
	[ResourceGroupID] INTEGER NOT NULL IDENTITY, 
	[SiteID] INTEGER NOT NULL, 
	[GroupCode] NVARCHAR(30) NOT NULL, 
	[GroupName] NVARCHAR(100) NOT NULL, 
	[SortOrder] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_ResourceGroups] PRIMARY KEY ([ResourceGroupID]), 
	CONSTRAINT [UQ_M_ResourceGroups_SiteID_GroupCode] UNIQUE ([SiteID], [GroupCode]), 
	CONSTRAINT [FK_M_ResourceGroups_SiteID_M_Sites] FOREIGN KEY([SiteID]) REFERENCES [M_Sites] ([SiteID])
);
GO

CREATE TABLE [M_Rules] (
	[RuleID] INTEGER NOT NULL IDENTITY, 
	[SiteID] INTEGER NOT NULL, 
	[RuleTypeKey] NVARCHAR(50) NOT NULL, 
	[RuleName] NVARCHAR(100) NOT NULL, 
	[SelectorJSON] NVARCHAR(max) NOT NULL, 
	[ParamsJSON] NVARCHAR(max) NOT NULL, 
	[IsHard] BIT NOT NULL, 
	[Weight] INTEGER NOT NULL, 
	[ValidFrom] DATETIME NULL, 
	[ValidTo] DATETIME NULL, 
	[IsActive] BIT NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_Rules] PRIMARY KEY ([RuleID]), 
	CONSTRAINT [FK_M_Rules_SiteID_M_Sites] FOREIGN KEY([SiteID]) REFERENCES [M_Sites] ([SiteID])
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
	[StartTime] DATETIME NOT NULL, 
	[EndTime] DATETIME NOT NULL, 
	[ShiftName] NVARCHAR(50) NULL, 
	[ValidFrom] DATETIME NULL, 
	[ValidTo] DATETIME NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_CalendarPatterns] PRIMARY KEY ([PatternID]), 
	CONSTRAINT [CK_M_CalendarPatterns_DayOfWeek] CHECK (DayOfWeek BETWEEN 1 AND 7), 
	CONSTRAINT [FK_M_CalendarPatterns_CalendarID_M_Calendars] FOREIGN KEY([CalendarID]) REFERENCES [M_Calendars] ([CalendarID]) ON DELETE CASCADE
);
GO

CREATE TABLE [M_ChangeoverMatrices] (
	[MatrixID] INTEGER NOT NULL IDENTITY, 
	[SiteID] INTEGER NOT NULL, 
	[MatrixName] NVARCHAR(100) NOT NULL, 
	[AttributeKey] NVARCHAR(50) NOT NULL, 
	[ResourceGroupID] INTEGER NULL, 
	[DefaultMinutes] INTEGER NOT NULL, 
	[IsActive] BIT NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_ChangeoverMatrices] PRIMARY KEY ([MatrixID]), 
	CONSTRAINT [FK_M_ChangeoverMatrices_SiteID_M_Sites] FOREIGN KEY([SiteID]) REFERENCES [M_Sites] ([SiteID]), 
	CONSTRAINT [FK_M_ChangeoverMatrices_ResourceGroupID_M_ResourceGroups] FOREIGN KEY([ResourceGroupID]) REFERENCES [M_ResourceGroups] ([ResourceGroupID])
);
GO

CREATE TABLE [M_Resources] (
	[ResourceID] INTEGER NOT NULL IDENTITY, 
	[SiteID] INTEGER NOT NULL, 
	[ResourceGroupID] INTEGER NULL, 
	[ResourceCode] NVARCHAR(30) NOT NULL, 
	[ResourceName] NVARCHAR(100) NOT NULL, 
	[ResourceType] NVARCHAR(20) NOT NULL, 
	[Capacity] NUMERIC(9, 2) NOT NULL, 
	[DailyCapacityHours] NUMERIC(5, 2) NULL, 
	[CalendarID] INTEGER NULL, 
	[CostPerHour] NUMERIC(12, 2) NULL, 
	[AttributesJSON] NVARCHAR(max) NULL, 
	[SortOrder] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Resources] PRIMARY KEY ([ResourceID]), 
	CONSTRAINT [UQ_M_Resources_SiteID_ResourceCode] UNIQUE ([SiteID], [ResourceCode]), 
	CONSTRAINT [CK_M_Resources_ResourceType] CHECK (ResourceType IN ('MACHINE','PERSON','TEAM','ROOM','OTHER')), 
	CONSTRAINT [FK_M_Resources_SiteID_M_Sites] FOREIGN KEY([SiteID]) REFERENCES [M_Sites] ([SiteID]), 
	CONSTRAINT [FK_M_Resources_ResourceGroupID_M_ResourceGroups] FOREIGN KEY([ResourceGroupID]) REFERENCES [M_ResourceGroups] ([ResourceGroupID]), 
	CONSTRAINT [FK_M_Resources_CalendarID_M_Calendars] FOREIGN KEY([CalendarID]) REFERENCES [M_Calendars] ([CalendarID])
);
GO

CREATE TABLE [M_Routings] (
	[RoutingID] INTEGER NOT NULL IDENTITY, 
	[ItemID] INTEGER NOT NULL, 
	[RoutingName] NVARCHAR(100) NOT NULL, 
	[Revision] INTEGER NOT NULL, 
	[IsDefault] BIT NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	[DeleteFlag] BIT NOT NULL, 
	CONSTRAINT [PK_M_Routings] PRIMARY KEY ([RoutingID]), 
	CONSTRAINT [UQ_M_Routings_ItemID_Revision] UNIQUE ([ItemID], [Revision]), 
	CONSTRAINT [FK_M_Routings_ItemID_M_Items] FOREIGN KEY([ItemID]) REFERENCES [M_Items] ([ItemID])
);
GO

CREATE TABLE [T_Plans] (
	[PlanID] INTEGER NOT NULL IDENTITY, 
	[SiteID] INTEGER NOT NULL, 
	[PlanNo] NVARCHAR(30) NOT NULL, 
	[PlanName] NVARCHAR(100) NOT NULL, 
	[Status] NVARCHAR(20) NOT NULL, 
	[HorizonStart] DATETIME2 NOT NULL, 
	[HorizonEnd] DATETIME2 NOT NULL, 
	[ProfileID] INTEGER NOT NULL, 
	[BasePlanID] INTEGER NULL, 
	[SupersededAt] DATETIME2 NULL, 
	[ApprovedAt] DATETIME2 NULL, 
	[ApprovedBy] NVARCHAR(254) NULL, 
	[Memo] NVARCHAR(500) NULL, 
	[RowVer] INTEGER NOT NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_T_Plans] PRIMARY KEY ([PlanID]), 
	CONSTRAINT [UQ_T_Plans_SiteID_PlanNo] UNIQUE ([SiteID], [PlanNo]), 
	CONSTRAINT [CK_T_Plans_Status] CHECK (Status IN ('DRAFT','MASTER','SUPERSEDED','DISCARDED','ARCHIVED')), 
	CONSTRAINT [FK_T_Plans_SiteID_M_Sites] FOREIGN KEY([SiteID]) REFERENCES [M_Sites] ([SiteID]), 
	CONSTRAINT [FK_T_Plans_ProfileID_M_PlanProfiles] FOREIGN KEY([ProfileID]) REFERENCES [M_PlanProfiles] ([ProfileID]), 
	CONSTRAINT [FK_T_Plans_BasePlanID_T_Plans] FOREIGN KEY([BasePlanID]) REFERENCES [T_Plans] ([PlanID])
);
GO

CREATE TABLE [M_ChangeoverEntries] (
	[EntryID] INTEGER NOT NULL IDENTITY, 
	[MatrixID] INTEGER NOT NULL, 
	[FromValue] NVARCHAR(50) NOT NULL, 
	[ToValue] NVARCHAR(50) NOT NULL, 
	[SetupMinutes] INTEGER NOT NULL, 
	[IsForbidden] BIT NOT NULL, 
	[Cost] NUMERIC(12, 2) NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_ChangeoverEntries] PRIMARY KEY ([EntryID]), 
	CONSTRAINT [UQ_M_ChangeoverEntries_MatrixID_FromValue_ToValue] UNIQUE ([MatrixID], [FromValue], [ToValue]), 
	CONSTRAINT [FK_M_ChangeoverEntries_MatrixID_M_ChangeoverMatrices] FOREIGN KEY([MatrixID]) REFERENCES [M_ChangeoverMatrices] ([MatrixID]) ON DELETE CASCADE
);
GO

CREATE TABLE [M_RoutingSteps] (
	[RoutingStepID] INTEGER NOT NULL IDENTITY, 
	[RoutingID] INTEGER NOT NULL, 
	[StepNo] INTEGER NOT NULL, 
	[StepName] NVARCHAR(100) NOT NULL, 
	[MinLagAfterMin] INTEGER NOT NULL, 
	[MaxLagAfterMin] INTEGER NULL, 
	[AttributesJSON] NVARCHAR(max) NULL, 
	[CreatedAt] DATETIME2 NOT NULL, 
	[CreatedBy] NVARCHAR(254) NULL, 
	[UpdatedAt] DATETIME2 NULL, 
	[UpdatedBy] NVARCHAR(254) NULL, 
	CONSTRAINT [PK_M_RoutingSteps] PRIMARY KEY ([RoutingStepID]), 
	CONSTRAINT [UQ_M_RoutingSteps_RoutingID_StepNo] UNIQUE ([RoutingID], [StepNo]), 
	CONSTRAINT [FK_M_RoutingSteps_RoutingID_M_Routings] FOREIGN KEY([RoutingID]) REFERENCES [M_Routings] ([RoutingID]) ON DELETE CASCADE
);
GO

CREATE TABLE [T_Orders] (
	[OrderID] INTEGER NOT NULL IDENTITY, 
	[SiteID] INTEGER NOT NULL, 
	[OrderNo] NVARCHAR(30) NOT NULL, 
	[OrderName] NVARCHAR(200) NOT NULL, 
	[OrderType] NVARCHAR(20) NOT NULL, 
	[ParentOrderID] INTEGER NULL, 
	[ItemID] INTEGER NULL, 
	[RoutingID] INTEGER NULL, 
	[Quantity] NUMERIC(18, 3) NULL, 
	[CustomerName] NVARCHAR(100) NULL, 
	[ReleaseAt] DATETIME2 NULL, 
	[DueAt] DATETIME2 NULL, 
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
	CONSTRAINT [UQ_T_Orders_SiteID_OrderNo] UNIQUE ([SiteID], [OrderNo]), 
	CONSTRAINT [CK_T_Orders_OrderType] CHECK (OrderType IN ('ORDER','PROJECT')), 
	CONSTRAINT [CK_T_Orders_Status] CHECK (Status IN ('OPEN','PLANNED','IN_PROGRESS','DONE','CANCELLED')), 
	CONSTRAINT [CK_T_Orders_PlanOwner] CHECK (PlanOwner IN ('SCHEDULER','EXTERNAL')), 
	CONSTRAINT [FK_T_Orders_SiteID_M_Sites] FOREIGN KEY([SiteID]) REFERENCES [M_Sites] ([SiteID]), 
	CONSTRAINT [FK_T_Orders_ParentOrderID_T_Orders] FOREIGN KEY([ParentOrderID]) REFERENCES [T_Orders] ([OrderID]), 
	CONSTRAINT [FK_T_Orders_ItemID_M_Items] FOREIGN KEY([ItemID]) REFERENCES [M_Items] ([ItemID]), 
	CONSTRAINT [FK_T_Orders_RoutingID_M_Routings] FOREIGN KEY([RoutingID]) REFERENCES [M_Routings] ([RoutingID])
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

CREATE TABLE [T_SolverRuns] (
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
	CONSTRAINT [PK_T_SolverRuns] PRIMARY KEY ([RunID]), 
	CONSTRAINT [CK_T_SolverRuns_Status] CHECK (Status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')), 
	CONSTRAINT [CK_T_SolverRuns_Scope] CHECK (Scope IN ('FULL','REPAIR')), 
	CONSTRAINT [FK_T_SolverRuns_PlanID_T_Plans] FOREIGN KEY([PlanID]) REFERENCES [T_Plans] ([PlanID])
);
GO

CREATE INDEX [IX_T_SolverRuns_Status_RequestedAt] ON [T_SolverRuns] ([Status], [RequestedAt]);
GO

CREATE TABLE [M_RoutingStepResources] (
	[RoutingStepResourceID] INTEGER NOT NULL IDENTITY, 
	[RoutingStepID] INTEGER NOT NULL, 
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
	CONSTRAINT [PK_M_RoutingStepResources] PRIMARY KEY ([RoutingStepResourceID]), 
	CONSTRAINT [CK_M_RoutingStepResources_ResourceOrGroup] CHECK ((ResourceID IS NULL AND ResourceGroupID IS NOT NULL) OR (ResourceID IS NOT NULL AND ResourceGroupID IS NULL)), 
	CONSTRAINT [FK_M_RoutingStepResources_RoutingStepID_M_RoutingSteps] FOREIGN KEY([RoutingStepID]) REFERENCES [M_RoutingSteps] ([RoutingStepID]) ON DELETE CASCADE, 
	CONSTRAINT [FK_M_RoutingStepResources_ResourceID_M_Resources] FOREIGN KEY([ResourceID]) REFERENCES [M_Resources] ([ResourceID]), 
	CONSTRAINT [FK_M_RoutingStepResources_ResourceGroupID_M_ResourceGroups] FOREIGN KEY([ResourceGroupID]) REFERENCES [M_ResourceGroups] ([ResourceGroupID])
);
GO

CREATE TABLE [T_Tasks] (
	[TaskID] INTEGER NOT NULL IDENTITY, 
	[OrderID] INTEGER NOT NULL, 
	[ParentTaskID] INTEGER NULL, 
	[RoutingStepID] INTEGER NULL, 
	[TaskNo] NVARCHAR(30) NOT NULL, 
	[TaskName] NVARCHAR(200) NOT NULL, 
	[Sequence] INTEGER NOT NULL, 
	[IsSummary] BIT NOT NULL, 
	[IsMilestone] BIT NOT NULL, 
	[EffortHours] NUMERIC(9, 2) NULL, 
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
	CONSTRAINT [FK_T_Tasks_ParentTaskID_T_Tasks] FOREIGN KEY([ParentTaskID]) REFERENCES [T_Tasks] ([TaskID]), 
	CONSTRAINT [FK_T_Tasks_RoutingStepID_M_RoutingSteps] FOREIGN KEY([RoutingStepID]) REFERENCES [M_RoutingSteps] ([RoutingStepID])
);
GO

CREATE TABLE [T_Actuals] (
	[ActualID] BIGINT NOT NULL IDENTITY, 
	[TaskID] INTEGER NOT NULL, 
	[ResourceID] INTEGER NULL, 
	[StartAt] DATETIME2 NULL, 
	[EndAt] DATETIME2 NULL, 
	[WorkDate] DATETIME NULL, 
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
	CONSTRAINT [PK_T_Actuals] PRIMARY KEY ([ActualID]), 
	CONSTRAINT [CK_T_Actuals_Status] CHECK (Status IN ('IN_PROGRESS','DONE','SUSPENDED')), 
	CONSTRAINT [CK_T_Actuals_Source] CHECK (Source IN ('MANUAL','PMS','IMPORT')), 
	CONSTRAINT [FK_T_Actuals_TaskID_T_Tasks] FOREIGN KEY([TaskID]) REFERENCES [T_Tasks] ([TaskID]), 
	CONSTRAINT [FK_T_Actuals_ResourceID_M_Resources] FOREIGN KEY([ResourceID]) REFERENCES [M_Resources] ([ResourceID])
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
	[ViolationCode] NVARCHAR(30) NOT NULL, 
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

ALTER TABLE [M_Sites] ADD CONSTRAINT [FK_M_Sites_DefaultCalendarID_M_Calendars] FOREIGN KEY([DefaultCalendarID]) REFERENCES [M_Calendars] ([CalendarID]);
GO
