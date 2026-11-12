-- DataBase/queryに配置した、SSMSで手動実行するデモデータ挿入SQL。
-- 新規作成した空のDB向け。既存データの変換は行わない。
-- 出荷日時ShippingDateは未指定（NULL）で登録する。日時の表示は共通の日本時間設定を使う。
-- 工程ルートの選択・版管理は行わず、工程を製品に直接紐づける。
-- 分類属性はタスクへ直接登録し、オーダーには種別・管理元・属性を登録しない。
-- 設備候補・工程順・待ち時間は製品マスタだけへ登録し、タスク用の複製は保存しない。
-- パン製造デモ：製品6種類、こねる → 焼く → 包装する。作業時間は仮設定。
-- 店舗納品を想定した名前の下書き計画2件を登録する。割付・評価値は画面で計算後に作成する。
-- このSQLの予定日は2026-10-30を基準に固定。Python実行時は登録日の翌日を基準にする。
USE [TONOPS-SCH];
GO
SET XACT_ABORT ON;
-- 独立した属性定義も確認し、登録済みデータへの追加を防ぐ。
IF EXISTS (SELECT 1 FROM [M_Locations])
    OR EXISTS (SELECT 1 FROM [M_AttributeDefinitions])
BEGIN
    THROW 50001, N'初期データは空のDBに対して実行してください。', 1;
END;
DECLARE @IdentityTable sysname = NULL;
DECLARE @CleanupSql nvarchar(512);
BEGIN TRY
BEGIN TRANSACTION;

-- M_AttributeDefinitions: 1件
SET @IdentityTable = N'M_AttributeDefinitions';
SET IDENTITY_INSERT [M_AttributeDefinitions] ON;
INSERT INTO [M_AttributeDefinitions] ([AttributeDefID], [EntityType], [AttributeKey], [Label], [DataType], [EnumValuesJSON], [IsRequired], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, N'TASK', N'family', N'パンの分類', N'ENUM', N'["食事パン", "菓子パン", "ナッツ入り"]', 0, 0, '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_AttributeDefinitions] OFF;
SET @IdentityTable = NULL;

-- M_Locations: 1件
SET @IdentityTable = N'M_Locations';
SET IDENTITY_INSERT [M_Locations] ON;
INSERT INTO [M_Locations] ([LocationID], [LocationName], [CalendarID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, N'パン工場', NULL, '2026-10-30T15:12:37.000000', N'seed', '2026-10-30T15:12:37.000000', NULL, 0);
SET IDENTITY_INSERT [M_Locations] OFF;
SET @IdentityTable = NULL;

-- 曜日番号：0=日、1=月、2=火、3=水、4=木、5=金、6=土。日曜は勤務を登録しない。
-- M_Calendars: 12件。同じ拠点の全勤務行を1組の週次カレンダーとして使う。
SET @IdentityTable = N'M_Calendars';
SET IDENTITY_INSERT [M_Calendars] ON;
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, 1, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, 1, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, 2, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 1, 2, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 1, 3, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 1, 3, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (7, 1, 4, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (8, 1, 4, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (9, 1, 5, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (10, 1, 5, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (11, 1, 6, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (12, 1, 6, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Calendars] OFF;
SET @IdentityTable = NULL;

-- M_Product: 6件
SET @IdentityTable = N'M_Product';
SET IDENTITY_INSERT [M_Product] ON;
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, N'食パン', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, N'バターロール', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, N'フランスパン', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 1, N'あんパン', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 1, N'メロンパン', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 1, N'くるみパン', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Product] OFF;
SET @IdentityTable = NULL;

-- M_CalculationSettings: 1件
SET @IdentityTable = N'M_CalculationSettings';
SET IDENTITY_INSERT [M_CalculationSettings] ON;
INSERT INTO [M_CalculationSettings] ([CalculationSettingID], [LocationID], [CalculationSettingName], [TimeUnit], [ObjectiveWeightsJSON], [FrozenWindowHours], [IsDefault], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, N'パン製造・納期優先', N'MINUTE', N'{"lateness": 1000, "setup": 10, "makespan": 1, "unscheduled": 100000}', 0, 1, '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_CalculationSettings] OFF;
SET @IdentityTable = NULL;

-- M_ResourceGroups: 3件
SET @IdentityTable = N'M_ResourceGroups';
SET IDENTITY_INSERT [M_ResourceGroups] ON;
INSERT INTO [M_ResourceGroups] ([ResourceGroupID], [LocationID], [GroupName], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, N'こねる設備', 0, '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_ResourceGroups] ([ResourceGroupID], [LocationID], [GroupName], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, N'焼く設備', 1, '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_ResourceGroups] ([ResourceGroupID], [LocationID], [GroupName], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, N'包装設備', 2, '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_ResourceGroups] OFF;
SET @IdentityTable = NULL;

-- M_Rules: 1件
SET @IdentityTable = N'M_Rules';
SET IDENTITY_INSERT [M_Rules] ON;
INSERT INTO [M_Rules] ([RuleID], [LocationID], [RuleTypeKey], [RuleName], [SelectorJSON], [ParamsJSON], [IsHard], [Weight], [ValidFrom], [ValidTo], [IsActive], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, N'allowed_weekdays', N'くるみパンは平日のみ製造（デモ）', N'{"family": "ナッツ入り"}', N'{"weekdays": [1, 2, 3, 4, 5]}', 1, 100, NULL, NULL, 1, '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_Rules] OFF;
SET @IdentityTable = NULL;

-- M_ProductSwitchTimes: 1件
SET @IdentityTable = N'M_ProductSwitchTimes';
SET IDENTITY_INSERT [M_ProductSwitchTimes] ON;
INSERT INTO [M_ProductSwitchTimes] ([ProductSwitchTimeID], [LocationID], [ProductSwitchTimeName], [AttributeKey], [ResourceGroupID], [DefaultMinutes], [IsActive], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, N'ミキサーのパン分類切替', N'family', 1, 0, 1, '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_ProductSwitchTimes] OFF;
SET @IdentityTable = NULL;

-- M_Resources: 6件
SET @IdentityTable = N'M_Resources';
SET IDENTITY_INSERT [M_Resources] ON;
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, 1, N'ミキサー1号機', 1.00, NULL, 0, '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, 1, N'ミキサー2号機', 1.00, NULL, 1, '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, 2, N'オーブン1号機', 1.00, NULL, 2, '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 1, 2, N'オーブン2号機', 1.00, NULL, 3, '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 1, 3, N'包装機1号機', 1.00, NULL, 4, '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 1, 3, N'包装機2号機', 1.00, NULL, 5, '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Resources] OFF;
SET @IdentityTable = NULL;

-- M_ProductSwitchRules: 6件
SET @IdentityTable = N'M_ProductSwitchRules';
SET IDENTITY_INSERT [M_ProductSwitchRules] ON;
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromValue], [ToValue], [SetupMinutes], [IsForbidden], [Cost], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, N'食事パン', N'菓子パン', 10, 0, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromValue], [ToValue], [SetupMinutes], [IsForbidden], [Cost], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 1, N'食事パン', N'ナッツ入り', 15, 0, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromValue], [ToValue], [SetupMinutes], [IsForbidden], [Cost], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 1, N'菓子パン', N'食事パン', 10, 0, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromValue], [ToValue], [SetupMinutes], [IsForbidden], [Cost], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 1, N'菓子パン', N'ナッツ入り', 15, 0, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromValue], [ToValue], [SetupMinutes], [IsForbidden], [Cost], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 1, N'ナッツ入り', N'食事パン', 20, 0, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromValue], [ToValue], [SetupMinutes], [IsForbidden], [Cost], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 1, N'ナッツ入り', N'菓子パン', 20, 0, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
SET IDENTITY_INSERT [M_ProductSwitchRules] OFF;
SET @IdentityTable = NULL;

-- M_ProductProcesses: 18件
SET @IdentityTable = N'M_ProductProcesses';
SET IDENTITY_INSERT [M_ProductProcesses] ON;
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, 1, N'こねる', 60, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 1, 2, N'焼く', 30, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 1, 3, N'包装する', 0, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 2, 1, N'こねる', 60, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 2, 2, N'焼く', 30, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 2, 3, N'包装する', 0, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (7, 3, 1, N'こねる', 60, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (8, 3, 2, N'焼く', 30, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (9, 3, 3, N'包装する', 0, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (10, 4, 1, N'こねる', 60, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (11, 4, 2, N'焼く', 30, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (12, 4, 3, N'包装する', 0, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (13, 5, 1, N'こねる', 60, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (14, 5, 2, N'焼く', 30, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (15, 5, 3, N'包装する', 0, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (16, 6, 1, N'こねる', 60, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (17, 6, 2, N'焼く', 30, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [MinLagAfterMin], [MaxLagAfterMin], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (18, 6, 3, N'包装する', 0, NULL, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
SET IDENTITY_INSERT [M_ProductProcesses] OFF;
SET @IdentityTable = NULL;

-- 作業者マスタの仮データ。今回は計画計算・CRUD API・画面には接続しない。
-- M_Workers: 3件
SET @IdentityTable = N'M_Workers';
SET IDENTITY_INSERT [M_Workers] ON;
INSERT INTO [M_Workers] ([WorkerID], [LocationID], [WorkerName], [Remarks], [DeleteFlag]) VALUES (1, 1, N'作業者A（こねる担当）', N'パン製造デモの作業者', 0);
INSERT INTO [M_Workers] ([WorkerID], [LocationID], [WorkerName], [Remarks], [DeleteFlag]) VALUES (2, 1, N'作業者B（焼く担当）', N'パン製造デモの作業者', 0);
INSERT INTO [M_Workers] ([WorkerID], [LocationID], [WorkerName], [Remarks], [DeleteFlag]) VALUES (3, 1, N'作業者C（包装担当）', N'パン製造デモの作業者', 0);
SET IDENTITY_INSERT [M_Workers] OFF;
SET @IdentityTable = NULL;

-- M_WorkerSkillMap: 54件。全工程分を登録し、可18件・不可36件を明示する。
SET @IdentityTable = N'M_WorkerSkillMap';
SET IDENTITY_INSERT [M_WorkerSkillMap] ON;
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (1, 1, 1, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (2, 2, 1, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (3, 3, 1, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (4, 1, 2, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (5, 2, 2, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (6, 3, 2, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (7, 1, 3, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (8, 2, 3, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (9, 3, 3, 1, 1200.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (10, 1, 4, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (11, 2, 4, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (12, 3, 4, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (13, 1, 5, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (14, 2, 5, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (15, 3, 5, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (16, 1, 6, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (17, 2, 6, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (18, 3, 6, 1, 1200.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (19, 1, 7, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (20, 2, 7, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (21, 3, 7, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (22, 1, 8, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (23, 2, 8, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (24, 3, 8, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (25, 1, 9, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (26, 2, 9, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (27, 3, 9, 1, 1200.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (28, 1, 10, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (29, 2, 10, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (30, 3, 10, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (31, 1, 11, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (32, 2, 11, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (33, 3, 11, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (34, 1, 12, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (35, 2, 12, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (36, 3, 12, 1, 1200.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (37, 1, 13, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (38, 2, 13, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (39, 3, 13, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (40, 1, 14, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (41, 2, 14, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (42, 3, 14, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (43, 1, 15, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (44, 2, 15, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (45, 3, 15, 1, 1200.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (46, 1, 16, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (47, 2, 16, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (48, 3, 16, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (49, 1, 17, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (50, 2, 17, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (51, 3, 17, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (52, 1, 18, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (53, 2, 18, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyQuantity], [Remarks]) VALUES (54, 3, 18, 1, 1200.000, NULL);
SET IDENTITY_INSERT [M_WorkerSkillMap] OFF;
SET @IdentityTable = NULL;

-- M_WorkerCalendars: 36件。月～土の06:00～12:00・13:00～18:00、日曜は休み。
SET @IdentityTable = N'M_WorkerCalendars';
SET IDENTITY_INSERT [M_WorkerCalendars] ON;
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, 1, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, 1, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, 2, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 1, 2, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 1, 3, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 1, 3, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (7, 1, 4, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (8, 1, 4, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (9, 1, 5, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (10, 1, 5, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (11, 1, 6, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (12, 1, 6, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (13, 2, 1, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (14, 2, 1, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (15, 2, 2, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (16, 2, 2, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (17, 2, 3, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (18, 2, 3, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (19, 2, 4, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (20, 2, 4, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (21, 2, 5, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (22, 2, 5, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (23, 2, 6, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (24, 2, 6, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (25, 3, 1, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (26, 3, 1, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (27, 3, 2, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (28, 3, 2, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (29, 3, 3, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (30, 3, 3, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (31, 3, 4, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (32, 3, 4, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (33, 3, 5, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (34, 3, 5, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (35, 3, 6, '06:00:00', '12:00:00', N'午前', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (36, 3, 6, '13:00:00', '18:00:00', N'午後', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_WorkerCalendars] OFF;
SET @IdentityTable = NULL;

-- M_WorkerCalendarExceptions: 1件。作業者Aの不在を、同作業者の勤務行へ関連付ける。
SET @IdentityTable = N'M_WorkerCalendarExceptions';
SET IDENTITY_INSERT [M_WorkerCalendarExceptions] ON;
INSERT INTO [M_WorkerCalendarExceptions] ([ExceptionID], [WorkerCalendarsID], [StartAt], [EndAt], [Remark], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, '2026-10-31T10:00:00', '2026-10-31T11:00:00', N'研修（デモ）', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_WorkerCalendarExceptions] OFF;
SET @IdentityTable = NULL;

-- T_Orders: 7件
SET @IdentityTable = N'T_Orders';
SET IDENTITY_INSERT [T_Orders] ON;
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, N'ORD-1001', N'食パン 200個（駅前店向け）', 1, 200.000, N'駅前店', '2026-10-31T06:00:00.000000', '2026-10-31T14:00:00.000000', NULL, 10, N'OPEN', NULL, '2026-10-30T15:12:37.000000', N'seed', '2026-10-30T15:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, N'ORD-1002', N'バターロール 300個（中央店向け）', 2, 300.000, N'中央店', '2026-10-31T06:00:00.000000', '2026-10-31T16:00:00.000000', NULL, 30, N'OPEN', NULL, '2026-10-30T15:12:37.000000', N'seed', '2026-10-30T15:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, N'ORD-1003', N'フランスパン 150個（駅前店向け）', 3, 150.000, N'駅前店', '2026-10-31T06:00:00.000000', '2026-10-31T16:00:00.000000', NULL, 30, N'OPEN', NULL, '2026-10-30T15:12:37.000000', N'seed', '2026-10-30T15:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 1, N'ORD-1004', N'あんパン 180個（中央店向け）', 4, 180.000, N'中央店', '2026-10-31T06:00:00.000000', '2026-10-31T18:00:00.000000', NULL, 20, N'OPEN', NULL, '2026-10-30T15:12:37.000000', N'seed', '2026-10-30T15:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 1, N'ORD-1005', N'メロンパン 120個（北口店向け）', 5, 120.000, N'北口店', '2026-10-31T06:00:00.000000', '2026-10-31T18:00:00.000000', NULL, 30, N'OPEN', NULL, '2026-10-30T15:12:37.000000', N'seed', '2026-10-30T15:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 1, N'ORD-1006', N'くるみパン 160個（北口店向け）', 6, 160.000, N'北口店', '2026-10-31T06:00:00.000000', '2026-11-02T16:00:00.000000', NULL, 40, N'OPEN', NULL, '2026-10-30T15:12:37.000000', N'seed', '2026-10-30T15:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (7, 1, N'ORD-1007', N'食パン 100個（中央店向け）', 1, 100.000, N'中央店', '2026-10-31T06:00:00.000000', '2026-11-01T14:00:00.000000', NULL, 50, N'OPEN', NULL, '2026-10-30T15:12:37.000000', N'seed', '2026-10-30T15:12:37.000000', NULL, 0);
SET IDENTITY_INSERT [T_Orders] OFF;
SET @IdentityTable = NULL;

-- M_ProductProcessResources: 18件
SET @IdentityTable = N'M_ProductProcessResources';
SET IDENTITY_INSERT [M_ProductProcessResources] ON;
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, NULL, 1, 10, 20, 0.0500, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 2, NULL, 2, 10, 25, 0.1000, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 3, NULL, 3, 5, 0, 0.1500, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 4, NULL, 1, 10, 20, 0.0500, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 5, NULL, 2, 10, 25, 0.1000, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 6, NULL, 3, 5, 0, 0.1500, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (7, 7, NULL, 1, 10, 20, 0.0500, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (8, 8, NULL, 2, 10, 25, 0.1000, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (9, 9, NULL, 3, 5, 0, 0.1500, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (10, 10, NULL, 1, 10, 20, 0.0500, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (11, 11, NULL, 2, 10, 25, 0.1000, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (12, 12, NULL, 3, 5, 0, 0.1500, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (13, 13, NULL, 1, 10, 20, 0.0500, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (14, 14, NULL, 2, 10, 25, 0.1000, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (15, 15, NULL, 3, 5, 0, 0.1500, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (16, 16, NULL, 1, 10, 20, 0.0500, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (17, 17, NULL, 2, 10, 25, 0.1000, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [SetupMinutes], [FixedMinutes], [MinutesPerUnit], [Priority], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (18, 18, NULL, 3, 5, 0, 0.1500, 1, '2026-10-30T15:12:37.000000', NULL, NULL, NULL);
SET IDENTITY_INSERT [M_ProductProcessResources] OFF;
SET @IdentityTable = NULL;

-- T_Tasks: 21件
SET @IdentityTable = N'T_Tasks';
SET IDENTITY_INSERT [T_Tasks] ON;
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, 1, N'1', N'こねる', 1, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 1, 2, N'2', N'焼く', 2, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 1, 3, N'3', N'包装する', 3, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 2, 4, N'1', N'こねる', 1, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 2, 5, N'2', N'焼く', 2, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 2, 6, N'3', N'包装する', 3, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (7, 3, 7, N'1', N'こねる', 1, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (8, 3, 8, N'2', N'焼く', 2, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (9, 3, 9, N'3', N'包装する', 3, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (10, 4, 10, N'1', N'こねる', 1, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "菓子パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (11, 4, 11, N'2', N'焼く', 2, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "菓子パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (12, 4, 12, N'3', N'包装する', 3, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "菓子パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (13, 5, 13, N'1', N'こねる', 1, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "菓子パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (14, 5, 14, N'2', N'焼く', 2, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "菓子パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (15, 5, 15, N'3', N'包装する', 3, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "菓子パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (16, 6, 16, N'1', N'こねる', 1, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "ナッツ入り"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (17, 6, 17, N'2', N'焼く', 2, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "ナッツ入り"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (18, 6, 18, N'3', N'包装する', 3, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "ナッツ入り"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (19, 7, 1, N'1', N'こねる', 1, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (20, 7, 2, N'2', N'焼く', 2, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskNo], [TaskName], [Sequence], [IsSummary], [EarliestStartAt], [DeadlineAt], [Status], [ProgressPct], [AttributesJSON], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (21, 7, 3, N'3', N'包装する', 3, 0, NULL, NULL, N'NOT_STARTED', 0.00, N'{"family": "食事パン"}', '2026-10-30T15:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [T_Tasks] OFF;
SET @IdentityTable = NULL;

-- T_Plans: 2件。Python版と同じ計画名・計算条件を使い、同じ拠点内で名前を重複させない。
-- 期間は既存オーダーと同じ現地2026-10-31 06:00から3日間。保存値は日本時間とする。
-- 計画はPlanIDとPlanNameで識別し、製造現場を想定した名前を設定する。
SET @IdentityTable = N'T_Plans';
SET IDENTITY_INSERT [T_Plans] ON;
INSERT INTO [T_Plans] ([PlanID], [LocationID], [PlanName], [Status], [StartAt], [EndAt], [CalculationSettingID], [BasePlanID], [Remarks], [RowVer], [CreatedAt], [CreatedBy]) VALUES (1, 1, N'各店舗向けパン製造・通常計画', N'DRAFT', '2026-10-31T06:00:00', '2026-11-03T06:00:00', 1, NULL, N'駅前店・中央店・北口店向けの食パン・菓子パンなどの製造計画。', 1, '2026-10-30T15:12:37.000000', N'seed');
INSERT INTO [T_Plans] ([PlanID], [LocationID], [PlanName], [Status], [StartAt], [EndAt], [CalculationSettingID], [BasePlanID], [Remarks], [RowVer], [CreatedAt], [CreatedBy]) VALUES (2, 1, N'各店舗向けパン製造・見直し計画', N'DRAFT', '2026-10-31T06:00:00', '2026-11-03T06:00:00', 1, NULL, N'駅前店・中央店・北口店向けの食パン・菓子パンなどの製造計画。', 1, '2026-10-30T15:12:37.000000', N'seed');
SET IDENTITY_INSERT [T_Plans] OFF;
SET @IdentityTable = NULL;

-- 拠点の代表勤務行を設定する。計算には同じLocationIDの全勤務行を使う。
UPDATE [M_Locations] SET [CalendarID] = 1 WHERE [LocationID] = 1;
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
