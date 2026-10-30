-- DataBase/queryに配置した、SSMSで手動実行するデモデータ挿入SQL。
-- 新規作成した空のDB向け。既存データの変換は行わない。
-- パン製造デモ：製品6種類、こねる → 焼く → 包装する。作業時間は仮設定。
-- このSQLの予定日は2026-10-30を基準に固定。Python実行時は登録日の翌日を基準にする。
USE [TONOPS-SCH];
GO
SET XACT_ABORT ON;
IF EXISTS (SELECT 1 FROM [M_Organizations])
BEGIN
    THROW 50001, N'初期データは空のDBに対して実行してください。', 1;
END;
DECLARE @IdentityTable sysname = NULL;
DECLARE @CleanupSql nvarchar(512);
BEGIN TRY
BEGIN TRANSACTION;

-- M_Organizations: 1件
SET @IdentityTable = N'M_Organizations';
SET IDENTITY_INSERT [M_Organizations] ON;
INSERT INTO [M_Organizations] ([OrganizationID], [OrganizationCode], [OrganizationName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, N'DEMO', N'デモベーカリー', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Organizations] OFF;
SET @IdentityTable = NULL;

-- M_AttributeDefinitions: 1件
SET @IdentityTable = N'M_AttributeDefinitions';
SET IDENTITY_INSERT [M_AttributeDefinitions] ON;
INSERT INTO [M_AttributeDefinitions] ([AttributeDefID], [OrganizationID], [EntityType], [AttributeKey], [Label], [DataType], [EnumValuesJSON], [IsRequired], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, N'PRODUCT', N'family', N'パンの分類', N'ENUM', N'["食事パン", "菓子パン", "ナッツ入り"]', 0, 0, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_AttributeDefinitions] OFF;
SET @IdentityTable = NULL;

-- M_Locations: 1件
SET @IdentityTable = N'M_Locations';
SET IDENTITY_INSERT [M_Locations] ON;
INSERT INTO [M_Locations] ([LocationID], [OrganizationID], [LocationCode], [LocationName], [TimeZone], [DefaultCalendarID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, N'BAKERY-A', N'パン工場', N'Asia/Tokyo', NULL, '2026-10-30T06:12:37.000000', N'seed', '2026-10-30T06:12:37.000000', NULL, 0);
SET IDENTITY_INSERT [M_Locations] OFF;
SET @IdentityTable = NULL;

-- M_Calendars: 1件
SET @IdentityTable = N'M_Calendars';
SET IDENTITY_INSERT [M_Calendars] ON;
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [CalendarCode], [CalendarName], [ParentCalendarID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, N'STD', N'パン工場標準カレンダー', NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Calendars] OFF;
SET @IdentityTable = NULL;

-- M_Product: 6件
SET @IdentityTable = N'M_Product';
SET IDENTITY_INSERT [M_Product] ON;
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductCode], [ProductName], [Unit], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, N'BREAD-001', N'食パン', N'個', N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductCode], [ProductName], [Unit], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, N'BREAD-002', N'バターロール', N'個', N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductCode], [ProductName], [Unit], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, N'BREAD-003', N'フランスパン', N'個', N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductCode], [ProductName], [Unit], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 1, N'BREAD-004', N'あんパン', N'個', N'{"family": "菓子パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductCode], [ProductName], [Unit], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 1, N'BREAD-005', N'メロンパン', N'個', N'{"family": "菓子パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductCode], [ProductName], [Unit], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 1, N'BREAD-006', N'くるみパン', N'個', N'{"family": "ナッツ入り"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Product] OFF;
SET @IdentityTable = NULL;

-- M_PlanProfiles: 1件
SET @IdentityTable = N'M_PlanProfiles';
SET IDENTITY_INSERT [M_PlanProfiles] ON;
INSERT INTO [M_PlanProfiles] ([ProfileID], [LocationID], [ProfileName], [TimeUnit], [ObjectiveWeightsJSON], [TimeLimitSec], [FrozenWindowHours], [IsDefault], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, N'パン製造・納期優先', N'MINUTE', N'{"lateness": 1000, "setup": 10, "makespan": 1, "unscheduled": 100000}', 30, 0, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_PlanProfiles] OFF;
SET @IdentityTable = NULL;

-- M_ResourceGroups: 3件
SET @IdentityTable = N'M_ResourceGroups';
SET IDENTITY_INSERT [M_ResourceGroups] ON;
INSERT INTO [M_ResourceGroups] ([ResourceGroupID], [LocationID], [GroupCode], [GroupName], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, N'KNEAD', N'こねる設備', 0, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_ResourceGroups] ([ResourceGroupID], [LocationID], [GroupCode], [GroupName], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, N'BAKE', N'焼く設備', 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_ResourceGroups] ([ResourceGroupID], [LocationID], [GroupCode], [GroupName], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, N'PACK', N'包装設備', 2, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_ResourceGroups] OFF;
SET @IdentityTable = NULL;

-- M_Rules: 1件
SET @IdentityTable = N'M_Rules';
SET IDENTITY_INSERT [M_Rules] ON;
INSERT INTO [M_Rules] ([RuleID], [LocationID], [RuleTypeKey], [RuleName], [SelectorJSON], [ParamsJSON], [IsHard], [Weight], [ValidFrom], [ValidTo], [IsActive], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, N'allowed_weekdays', N'くるみパンは平日のみ製造（デモ）', N'{"family": "ナッツ入り"}', N'{"weekdays": [1, 2, 3, 4, 5]}', 1, 100, NULL, NULL, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_Rules] OFF;
SET @IdentityTable = NULL;

-- M_CalendarPatterns: 12件
SET @IdentityTable = N'M_CalendarPatterns';
SET IDENTITY_INSERT [M_CalendarPatterns] ON;
INSERT INTO [M_CalendarPatterns] ([PatternID], [CalendarID], [DayOfWeek], [StartTime], [EndTime], [ShiftName], [ValidFrom], [ValidTo], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, 1, '06:00:00', '12:00:00', N'午前', NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_CalendarPatterns] ([PatternID], [CalendarID], [DayOfWeek], [StartTime], [EndTime], [ShiftName], [ValidFrom], [ValidTo], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 1, 1, '13:00:00', '18:00:00', N'午後', NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_CalendarPatterns] ([PatternID], [CalendarID], [DayOfWeek], [StartTime], [EndTime], [ShiftName], [ValidFrom], [ValidTo], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 1, 2, '06:00:00', '12:00:00', N'午前', NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_CalendarPatterns] ([PatternID], [CalendarID], [DayOfWeek], [StartTime], [EndTime], [ShiftName], [ValidFrom], [ValidTo], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 1, 2, '13:00:00', '18:00:00', N'午後', NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_CalendarPatterns] ([PatternID], [CalendarID], [DayOfWeek], [StartTime], [EndTime], [ShiftName], [ValidFrom], [ValidTo], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 1, 3, '06:00:00', '12:00:00', N'午前', NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_CalendarPatterns] ([PatternID], [CalendarID], [DayOfWeek], [StartTime], [EndTime], [ShiftName], [ValidFrom], [ValidTo], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 1, 3, '13:00:00', '18:00:00', N'午後', NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_CalendarPatterns] ([PatternID], [CalendarID], [DayOfWeek], [StartTime], [EndTime], [ShiftName], [ValidFrom], [ValidTo], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (7, 1, 4, '06:00:00', '12:00:00', N'午前', NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_CalendarPatterns] ([PatternID], [CalendarID], [DayOfWeek], [StartTime], [EndTime], [ShiftName], [ValidFrom], [ValidTo], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (8, 1, 4, '13:00:00', '18:00:00', N'午後', NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_CalendarPatterns] ([PatternID], [CalendarID], [DayOfWeek], [StartTime], [EndTime], [ShiftName], [ValidFrom], [ValidTo], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (9, 1, 5, '06:00:00', '12:00:00', N'午前', NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_CalendarPatterns] ([PatternID], [CalendarID], [DayOfWeek], [StartTime], [EndTime], [ShiftName], [ValidFrom], [ValidTo], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (10, 1, 5, '13:00:00', '18:00:00', N'午後', NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_CalendarPatterns] ([PatternID], [CalendarID], [DayOfWeek], [StartTime], [EndTime], [ShiftName], [ValidFrom], [ValidTo], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (11, 1, 6, '06:00:00', '12:00:00', N'午前', NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_CalendarPatterns] ([PatternID], [CalendarID], [DayOfWeek], [StartTime], [EndTime], [ShiftName], [ValidFrom], [ValidTo], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (12, 1, 6, '13:00:00', '18:00:00', N'午後', NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
SET IDENTITY_INSERT [M_CalendarPatterns] OFF;
SET @IdentityTable = NULL;

-- M_ChangeoverMatrices: 1件
SET @IdentityTable = N'M_ChangeoverMatrices';
SET IDENTITY_INSERT [M_ChangeoverMatrices] ON;
INSERT INTO [M_ChangeoverMatrices] ([MatrixID], [LocationID], [MatrixName], [AttributeKey], [ResourceGroupID], [DefaultMinutes], [IsActive], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, N'ミキサーのパン分類切替', N'family', 1, 0, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_ChangeoverMatrices] OFF;
SET @IdentityTable = NULL;

-- M_Resources: 6件
SET @IdentityTable = N'M_Resources';
SET IDENTITY_INSERT [M_Resources] ON;
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceCode], [ResourceName], [ResourceType], [Capacity], [DailyCapacityHours], [CalendarID], [CostPerHour], [AttributesJSON], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, 1, N'KN-01', N'ミキサー1号機', N'MACHINE', 1.00, NULL, 1, NULL, NULL, 0, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceCode], [ResourceName], [ResourceType], [Capacity], [DailyCapacityHours], [CalendarID], [CostPerHour], [AttributesJSON], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, 1, N'KN-02', N'ミキサー2号機', N'MACHINE', 1.00, NULL, 1, NULL, NULL, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceCode], [ResourceName], [ResourceType], [Capacity], [DailyCapacityHours], [CalendarID], [CostPerHour], [AttributesJSON], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, 2, N'OV-01', N'オーブン1号機', N'MACHINE', 1.00, NULL, 1, NULL, NULL, 2, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceCode], [ResourceName], [ResourceType], [Capacity], [DailyCapacityHours], [CalendarID], [CostPerHour], [AttributesJSON], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 1, 2, N'OV-02', N'オーブン2号機', N'MACHINE', 1.00, NULL, 1, NULL, NULL, 3, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceCode], [ResourceName], [ResourceType], [Capacity], [DailyCapacityHours], [CalendarID], [CostPerHour], [AttributesJSON], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 1, 3, N'PK-01', N'包装機1号機', N'MACHINE', 1.00, NULL, 1, NULL, NULL, 4, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceCode], [ResourceName], [ResourceType], [Capacity], [DailyCapacityHours], [CalendarID], [CostPerHour], [AttributesJSON], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 1, 3, N'PK-02', N'包装機2号機', N'MACHINE', 1.00, NULL, 1, NULL, NULL, 5, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Resources] OFF;
SET @IdentityTable = NULL;

-- M_Routings: 6件
SET @IdentityTable = N'M_Routings';
SET IDENTITY_INSERT [M_Routings] ON;
INSERT INTO [M_Routings] ([RoutingID], [ProductID], [RoutingName], [Revision], [IsDefault], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, N'食パン：こねる → 焼く → 包装する', 1, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Routings] ([RoutingID], [ProductID], [RoutingName], [Revision], [IsDefault], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 2, N'バターロール：こねる → 焼く → 包装する', 1, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Routings] ([RoutingID], [ProductID], [RoutingName], [Revision], [IsDefault], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 3, N'フランスパン：こねる → 焼く → 包装する', 1, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Routings] ([RoutingID], [ProductID], [RoutingName], [Revision], [IsDefault], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 4, N'あんパン：こねる → 焼く → 包装する', 1, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Routings] ([RoutingID], [ProductID], [RoutingName], [Revision], [IsDefault], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 5, N'メロンパン：こねる → 焼く → 包装する', 1, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Routings] ([RoutingID], [ProductID], [RoutingName], [Revision], [IsDefault], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 6, N'くるみパン：こねる → 焼く → 包装する', 1, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Routings] OFF;
SET @IdentityTable = NULL;

-- M_ChangeoverEntries: 6件
SET @IdentityTable = N'M_ChangeoverEntries';
SET IDENTITY_INSERT [M_ChangeoverEntries] ON;
INSERT INTO [M_ChangeoverEntries] ([EntryID], [MatrixID], [FromValue], [ToValue], [SetupMinutes], [IsForbidden], [Cost], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, N'食事パン', N'菓子パン', 10, 0, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ChangeoverEntries] ([EntryID], [MatrixID], [FromValue], [ToValue], [SetupMinutes], [IsForbidden], [Cost], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 1, N'食事パン', N'ナッツ入り', 15, 0, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ChangeoverEntries] ([EntryID], [MatrixID], [FromValue], [ToValue], [SetupMinutes], [IsForbidden], [Cost], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 1, N'菓子パン', N'食事パン', 10, 0, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ChangeoverEntries] ([EntryID], [MatrixID], [FromValue], [ToValue], [SetupMinutes], [IsForbidden], [Cost], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 1, N'菓子パン', N'ナッツ入り', 15, 0, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ChangeoverEntries] ([EntryID], [MatrixID], [FromValue], [ToValue], [SetupMinutes], [IsForbidden], [Cost], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 1, N'ナッツ入り', N'食事パン', 20, 0, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ChangeoverEntries] ([EntryID], [MatrixID], [FromValue], [ToValue], [SetupMinutes], [IsForbidden], [Cost], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 1, N'ナッツ入り', N'菓子パン', 20, 0, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
SET IDENTITY_INSERT [M_ChangeoverEntries] OFF;
SET @IdentityTable = NULL;

-- M_RoutingSteps: 18件
SET @IdentityTable = N'M_RoutingSteps';
SET IDENTITY_INSERT [M_RoutingSteps] ON;
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, 10, N'こねる', 60, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 1, 20, N'焼く', 30, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 1, 30, N'包装する', 0, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 2, 10, N'こねる', 60, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 2, 20, N'焼く', 30, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 2, 30, N'包装する', 0, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (7, 3, 10, N'こねる', 60, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (8, 3, 20, N'焼く', 30, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (9, 3, 30, N'包装する', 0, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (10, 4, 10, N'こねる', 60, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (11, 4, 20, N'焼く', 30, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (12, 4, 30, N'包装する', 0, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (13, 5, 10, N'こねる', 60, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (14, 5, 20, N'焼く', 30, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (15, 5, 30, N'包装する', 0, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (16, 6, 10, N'こねる', 60, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (17, 6, 20, N'焼く', 30, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingSteps] ([RoutingStepID], [RoutingID], [StepNo], [StepName], [MinLagAfterMin], [MaxLagAfterMin], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (18, 6, 30, N'包装する', 0, NULL, NULL, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
SET IDENTITY_INSERT [M_RoutingSteps] OFF;
SET @IdentityTable = NULL;

-- T_Orders: 7件
SET @IdentityTable = N'T_Orders';
SET IDENTITY_INSERT [T_Orders] ON;
INSERT INTO [T_Orders] ([OrderID], [LocationID], [OrderNo], [OrderName], [OrderType], [ParentOrderID], [ProductID], [RoutingID], [Quantity], [CustomerName], [ReleaseAt], [DueAt], [Priority], [Status], [PlanOwner], [AttributesJSON], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, N'ORD-1001', N'食パン 200個（駅前店向け）', N'ORDER', NULL, 1, 1, 200.000, N'駅前店', '2026-10-30T21:00:00.000000', '2026-10-31T05:00:00.000000', 10, N'OPEN', N'SCHEDULER', NULL, NULL, '2026-10-30T06:12:37.000000', N'seed', '2026-10-30T06:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [OrderNo], [OrderName], [OrderType], [ParentOrderID], [ProductID], [RoutingID], [Quantity], [CustomerName], [ReleaseAt], [DueAt], [Priority], [Status], [PlanOwner], [AttributesJSON], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, N'ORD-1002', N'バターロール 300個（中央店向け）', N'ORDER', NULL, 2, 2, 300.000, N'中央店', '2026-10-30T21:00:00.000000', '2026-10-31T07:00:00.000000', 30, N'OPEN', N'SCHEDULER', NULL, NULL, '2026-10-30T06:12:37.000000', N'seed', '2026-10-30T06:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [OrderNo], [OrderName], [OrderType], [ParentOrderID], [ProductID], [RoutingID], [Quantity], [CustomerName], [ReleaseAt], [DueAt], [Priority], [Status], [PlanOwner], [AttributesJSON], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, N'ORD-1003', N'フランスパン 150個（駅前店向け）', N'ORDER', NULL, 3, 3, 150.000, N'駅前店', '2026-10-30T21:00:00.000000', '2026-10-31T07:00:00.000000', 30, N'OPEN', N'SCHEDULER', NULL, NULL, '2026-10-30T06:12:37.000000', N'seed', '2026-10-30T06:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [OrderNo], [OrderName], [OrderType], [ParentOrderID], [ProductID], [RoutingID], [Quantity], [CustomerName], [ReleaseAt], [DueAt], [Priority], [Status], [PlanOwner], [AttributesJSON], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 1, N'ORD-1004', N'あんパン 180個（中央店向け）', N'ORDER', NULL, 4, 4, 180.000, N'中央店', '2026-10-30T21:00:00.000000', '2026-10-31T09:00:00.000000', 20, N'OPEN', N'SCHEDULER', NULL, NULL, '2026-10-30T06:12:37.000000', N'seed', '2026-10-30T06:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [OrderNo], [OrderName], [OrderType], [ParentOrderID], [ProductID], [RoutingID], [Quantity], [CustomerName], [ReleaseAt], [DueAt], [Priority], [Status], [PlanOwner], [AttributesJSON], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 1, N'ORD-1005', N'メロンパン 120個（北口店向け）', N'ORDER', NULL, 5, 5, 120.000, N'北口店', '2026-10-30T21:00:00.000000', '2026-10-31T09:00:00.000000', 30, N'OPEN', N'SCHEDULER', NULL, NULL, '2026-10-30T06:12:37.000000', N'seed', '2026-10-30T06:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [OrderNo], [OrderName], [OrderType], [ParentOrderID], [ProductID], [RoutingID], [Quantity], [CustomerName], [ReleaseAt], [DueAt], [Priority], [Status], [PlanOwner], [AttributesJSON], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 1, N'ORD-1006', N'くるみパン 160個（北口店向け）', N'ORDER', NULL, 6, 6, 160.000, N'北口店', '2026-10-30T21:00:00.000000', '2026-11-02T07:00:00.000000', 40, N'OPEN', N'SCHEDULER', NULL, NULL, '2026-10-30T06:12:37.000000', N'seed', '2026-10-30T06:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [OrderNo], [OrderName], [OrderType], [ParentOrderID], [ProductID], [RoutingID], [Quantity], [CustomerName], [ReleaseAt], [DueAt], [Priority], [Status], [PlanOwner], [AttributesJSON], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (7, 1, N'ORD-1007', N'食パン 100個（中央店向け）', N'ORDER', NULL, 1, 1, 100.000, N'中央店', '2026-10-30T21:00:00.000000', '2026-11-01T05:00:00.000000', 50, N'OPEN', N'SCHEDULER', NULL, NULL, '2026-10-30T06:12:37.000000', N'seed', '2026-10-30T06:12:37.000000', NULL, 0);
SET IDENTITY_INSERT [T_Orders] OFF;
SET @IdentityTable = NULL;

-- M_RoutingStepResources: 18件
SET @IdentityTable = N'M_RoutingStepResources';
SET IDENTITY_INSERT [M_RoutingStepResources] ON;
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, NULL, 1, 10, 20, 0.0500, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 2, NULL, 2, 10, 25, 0.1000, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 3, NULL, 3, 5, 0, 0.1500, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 4, NULL, 1, 10, 20, 0.0500, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 5, NULL, 2, 10, 25, 0.1000, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 6, NULL, 3, 5, 0, 0.1500, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (7, 7, NULL, 1, 10, 20, 0.0500, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (8, 8, NULL, 2, 10, 25, 0.1000, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (9, 9, NULL, 3, 5, 0, 0.1500, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (10, 10, NULL, 1, 10, 20, 0.0500, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (11, 11, NULL, 2, 10, 25, 0.1000, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (12, 12, NULL, 3, 5, 0, 0.1500, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (13, 13, NULL, 1, 10, 20, 0.0500, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (14, 14, NULL, 2, 10, 25, 0.1000, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (15, 15, NULL, 3, 5, 0, 0.1500, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (16, 16, NULL, 1, 10, 20, 0.0500, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (17, 17, NULL, 2, 10, 25, 0.1000, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_RoutingStepResources] ([RoutingStepResourceID], [RoutingStepID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (18, 18, NULL, 3, 5, 0, 0.1500, 1, '2026-10-30T06:12:37.000000', NULL, NULL, NULL);
SET IDENTITY_INSERT [M_RoutingStepResources] OFF;
SET @IdentityTable = NULL;

-- T_Tasks: 21件
SET @IdentityTable = N'T_Tasks';
SET IDENTITY_INSERT [T_Tasks] ON;
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, NULL, 1, N'10', N'こねる', 1, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 1, NULL, 2, N'20', N'焼く', 2, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 1, NULL, 3, N'30', N'包装する', 3, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 2, NULL, 4, N'10', N'こねる', 1, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 2, NULL, 5, N'20', N'焼く', 2, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 2, NULL, 6, N'30', N'包装する', 3, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (7, 3, NULL, 7, N'10', N'こねる', 1, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (8, 3, NULL, 8, N'20', N'焼く', 2, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (9, 3, NULL, 9, N'30', N'包装する', 3, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (10, 4, NULL, 10, N'10', N'こねる', 1, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "菓子パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (11, 4, NULL, 11, N'20', N'焼く', 2, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "菓子パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (12, 4, NULL, 12, N'30', N'包装する', 3, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "菓子パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (13, 5, NULL, 13, N'10', N'こねる', 1, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "菓子パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (14, 5, NULL, 14, N'20', N'焼く', 2, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "菓子パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (15, 5, NULL, 15, N'30', N'包装する', 3, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "菓子パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (16, 6, NULL, 16, N'10', N'こねる', 1, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "ナッツ入り"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (17, 6, NULL, 17, N'20', N'焼く', 2, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "ナッツ入り"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (18, 6, NULL, 18, N'30', N'包装する', 3, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "ナッツ入り"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (19, 7, NULL, 1, N'10', N'こねる', 1, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (20, 7, NULL, 2, N'20', N'焼く', 2, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ParentTaskID], [RoutingStepID], [TaskNo], [TaskName], [Sequence], [IsSummary], [IsMilestone], [EffortHours], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (21, 7, NULL, 3, N'30', N'包装する', 3, 0, 0, NULL, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [T_Tasks] OFF;
SET @IdentityTable = NULL;

-- T_TaskDependencies: 14件
SET @IdentityTable = N'T_TaskDependencies';
SET IDENTITY_INSERT [T_TaskDependencies] ON;
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, 2, N'FS', 60, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 2, 3, N'FS', 30, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 4, 5, N'FS', 60, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 5, 6, N'FS', 30, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 7, 8, N'FS', 60, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 8, 9, N'FS', 30, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (7, 10, 11, N'FS', 60, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (8, 11, 12, N'FS', 30, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (9, 13, 14, N'FS', 60, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (10, 14, 15, N'FS', 30, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (11, 16, 17, N'FS', 60, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (12, 17, 18, N'FS', 30, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (13, 19, 20, N'FS', 60, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskDependencies] ([DependencyID], [PredecessorTaskID], [SuccessorTaskID], [DependencyType], [LagMin], [MaxLagMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (14, 20, 21, N'FS', 30, NULL, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [T_TaskDependencies] OFF;
SET @IdentityTable = NULL;

-- T_TaskResourceOptions: 21件
SET @IdentityTable = N'T_TaskResourceOptions';
SET IDENTITY_INSERT [T_TaskResourceOptions] ON;
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, NULL, 1, 40, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 2, NULL, 2, 55, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 3, NULL, 3, 35, 5, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 4, NULL, 1, 45, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 5, NULL, 2, 65, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 6, NULL, 3, 50, 5, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (7, 7, NULL, 1, 38, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (8, 8, NULL, 2, 50, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (9, 9, NULL, 3, 28, 5, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (10, 10, NULL, 1, 39, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (11, 11, NULL, 2, 53, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (12, 12, NULL, 3, 32, 5, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (13, 13, NULL, 1, 36, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (14, 14, NULL, 2, 47, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (15, 15, NULL, 3, 23, 5, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (16, 16, NULL, 1, 38, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (17, 17, NULL, 2, 51, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (18, 18, NULL, 3, 29, 5, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (19, 19, NULL, 1, 35, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (20, 20, NULL, 2, 45, 10, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_TaskResourceOptions] ([OptionID], [TaskID], [ResourceID], [ResourceGroupID], [DurationMin], [SetupMinutes], [Units], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (21, 21, NULL, 3, 20, 5, 1.00, 1, '2026-10-30T06:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [T_TaskResourceOptions] OFF;
SET @IdentityTable = NULL;

-- 拠点の標準カレンダー等、後から参照先ができる項目を設定する。
UPDATE [M_Locations] SET [DefaultCalendarID] = 1 WHERE [LocationID] = 1;
COMMIT TRANSACTION;
END TRY
BEGIN CATCH
IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
IF @IdentityTable IS NOT NULL
BEGIN
    SET @CleanupSql = N'SET IDENTITY_INSERT ' + QUOTENAME(@IdentityTable) + N' OFF;';
    EXEC sys.sp_executesql @CleanupSql;
END;
THROW;
END CATCH;
GO
