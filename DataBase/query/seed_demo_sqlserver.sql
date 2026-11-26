-- 段取り替え明細は、参照する製品工程を登録した後に挿入する。
-- SSMSの手動実行と、python -m DataBase.setup_databaseのSQL Server初期設定で共用する仮データ挿入SQL。
-- 新規作成した空のDBへ仮データを登録する。
-- 出荷日時ShippingDateは未指定（NULL）で登録する。日時の表示は共通の日本時間設定を使う。
-- 工程ルートの選択・版管理は行わず、工程を製品に直接紐づける。
-- タスクはTaskIDで識別し、作業番号・集約指定・進捗率・属性は登録しない。
-- 設備候補・工程順・待ち時間は製品マスタだけへ登録し、タスク用の複製は保存しない。
-- 準備・固定・数量当たり時間は工程に登録し、すべての設備候補で共用する。
-- 作業時間はProcessingMinutes。包装工程の固定時間はNULLとし、計算時に0分として扱う。
-- パン製造デモ：製品6種類、こねる → 焼く → 包装する。作業時間は仮設定。
-- 比較撮影用の下書き計画2件と割付・評価値を登録する。計算を実行せず比較画面を開ける。
-- このSQLの予定日は2026-11-15を基準に固定。Python版も同じ固定日を使う。
USE [TONOPS-SCH];
GO
SET XACT_ABORT ON;
-- 拠点の登録を確認し、登録済みデータへの追加を防ぐ。
IF EXISTS (SELECT 1 FROM [M_Locations])
BEGIN
    THROW 50001, N'初期データは空のDBに対して実行してください。', 1;
END;
DECLARE @IdentityTable sysname = NULL;
DECLARE @CleanupSql nvarchar(512);
BEGIN TRY
BEGIN TRANSACTION;

-- M_Locations: 2件（パン工場は分単位、センシングは日単位）
SET @IdentityTable = N'M_Locations';
SET IDENTITY_INSERT [M_Locations] ON;
INSERT INTO [M_Locations] ([LocationID], [LocationName], [LocationTimeUnit], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, N'パン工場', N'MINUTE', '2026-11-15T15:12:37.000000', N'seed', '2026-11-15T15:12:37.000000', NULL, 0);
INSERT INTO [M_Locations] ([LocationID], [LocationName], [LocationTimeUnit], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, N'センシング', N'DAY', '2026-11-19T00:00:00.0000000', N'test', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Locations] OFF;
SET @IdentityTable = NULL;

-- 曜日番号：0=日、1=月、2=火、3=水、4=木、5=金、6=土。日曜は勤務を登録しない。
-- M_Calendars: 12件。同じ拠点の全勤務行を1組の週次カレンダーとして使う。
SET @IdentityTable = N'M_Calendars';
SET IDENTITY_INSERT [M_Calendars] ON;
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, 1, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, 1, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, 2, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 1, 2, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 1, 3, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 1, 3, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (7, 1, 4, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (8, 1, 4, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (9, 1, 5, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (10, 1, 5, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (11, 1, 6, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (12, 1, 6, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Calendars] OFF;
SET @IdentityTable = NULL;

-- M_Product: 6件。任意の品目コードはBREAD-001～BREAD-006を登録する。
SET @IdentityTable = N'M_Product';
SET IDENTITY_INSERT [M_Product] ON;
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [ProductCode], [ExcludeFromDailyCap], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, N'食パン', N'BREAD-001', 0, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [ProductCode], [ExcludeFromDailyCap], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, N'バターロール', N'BREAD-002', 0, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [ProductCode], [ExcludeFromDailyCap], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, N'フランスパン', N'BREAD-003', 0, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [ProductCode], [ExcludeFromDailyCap], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 1, N'あんパン', N'BREAD-004', 0, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [ProductCode], [ExcludeFromDailyCap], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 1, N'メロンパン', N'BREAD-005', 0, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [ProductCode], [ExcludeFromDailyCap], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 1, N'くるみパン', N'BREAD-006', 0, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Product] OFF;
SET @IdentityTable = NULL;

-- M_CalculationSettings: 1件
SET @IdentityTable = N'M_CalculationSettings';
SET IDENTITY_INSERT [M_CalculationSettings] ON;
INSERT INTO [M_CalculationSettings] ([CalculationSettingID], [LocationID], [CalculationSettingName], [TimeUnit], [ObjectiveWeightsJSON], [FrozenWindowHours], [IsDefault], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, N'パン製造・納期優先', N'MINUTE', N'{"lateness": 1000, "setup": 10, "makespan": 1, "unscheduled": 100000}', 0, 1, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_CalculationSettings] OFF;
SET @IdentityTable = NULL;

-- M_ResourceGroups: 3件
SET @IdentityTable = N'M_ResourceGroups';
SET IDENTITY_INSERT [M_ResourceGroups] ON;
INSERT INTO [M_ResourceGroups] ([ResourceGroupID], [LocationID], [GroupName], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, N'こねる設備', 1, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_ResourceGroups] ([ResourceGroupID], [LocationID], [GroupName], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, N'焼く設備', 2, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_ResourceGroups] ([ResourceGroupID], [LocationID], [GroupName], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, N'包装設備', 3, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_ResourceGroups] OFF;
SET @IdentityTable = NULL;

-- M_ProductSwitchTimes: 有効なグループ設定1件。無効な単体設定1件はリソース登録後に追加する。
SET @IdentityTable = N'M_ProductSwitchTimes';
SET IDENTITY_INSERT [M_ProductSwitchTimes] ON;
INSERT INTO [M_ProductSwitchTimes] ([ProductSwitchTimeID], [LocationID], [ProductSwitchTimeName], [ResourceID], [ResourceGroupID], [DefaultMinutes], [IsActive], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, N'ミキサーの製品工程切替条件', NULL, 1, 0, 1, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_ProductSwitchTimes] OFF;
SET @IdentityTable = NULL;

-- M_Resources: 6件（Capacity・DailyCapacityQuantityはNULL）
SET @IdentityTable = N'M_Resources';
SET IDENTITY_INSERT [M_Resources] ON;
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [DailyCapacityQuantity], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, 1, N'ミキサー1号機', NULL, NULL, NULL, 1, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [DailyCapacityQuantity], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, 1, N'ミキサー2号機', NULL, NULL, NULL, 2, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [DailyCapacityQuantity], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, 2, N'オーブン1号機', NULL, NULL, NULL, 3, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [DailyCapacityQuantity], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 1, 2, N'オーブン2号機', NULL, NULL, NULL, 4, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [DailyCapacityQuantity], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 1, 3, N'包装機1号機', NULL, NULL, NULL, 5, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [DailyCapacityQuantity], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 1, 3, N'包装機2号機', NULL, NULL, NULL, 6, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Resources] OFF;
SET @IdentityTable = NULL;

-- 単体指定の設定例。既存の有効なグループ設定と重複するため、無効で登録する。
SET @IdentityTable = N'M_ProductSwitchTimes';
SET IDENTITY_INSERT [M_ProductSwitchTimes] ON;
INSERT INTO [M_ProductSwitchTimes] ([ProductSwitchTimeID], [LocationID], [ProductSwitchTimeName], [ResourceID], [ResourceGroupID], [DefaultMinutes], [IsActive], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 1, N'ミキサー1号機の切替条件（設定例）', 1, NULL, 0, 0, '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_ProductSwitchTimes] OFF;
SET @IdentityTable = NULL;

-- M_ProductProcesses: 18件（パン工場は分単位計算用のため日単位項目は既定値・MaxHolidaysAfterはNULL）
SET @IdentityTable = N'M_ProductProcesses';
SET IDENTITY_INSERT [M_ProductProcesses] ON;
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, 1, N'こねる', NULL, 10, 20, 0.0500, 60, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 1, 2, N'焼く', NULL, 10, 25, 0.1000, 30, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 1, 3, N'包装する', NULL, 5, NULL, 0.1500, 0, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 2, 1, N'こねる', NULL, 10, 20, 0.0500, 60, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 2, 2, N'焼く', NULL, 10, 25, 0.1000, 30, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 2, 3, N'包装する', NULL, 5, NULL, 0.1500, 0, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (7, 3, 1, N'こねる', NULL, 10, 20, 0.0500, 60, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (8, 3, 2, N'焼く', NULL, 10, 25, 0.1000, 30, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (9, 3, 3, N'包装する', NULL, 5, NULL, 0.1500, 0, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (10, 4, 1, N'こねる', NULL, 10, 20, 0.0500, 60, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (11, 4, 2, N'焼く', NULL, 10, 25, 0.1000, 30, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (12, 4, 3, N'包装する', NULL, 5, NULL, 0.1500, 0, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (13, 5, 1, N'こねる', NULL, 10, 20, 0.0500, 60, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (14, 5, 2, N'焼く', NULL, 10, 25, 0.1000, 30, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (15, 5, 3, N'包装する', NULL, 5, NULL, 0.1500, 0, NULL, NULL, 1, 0, NULL, NULL, N'[0,1,2,3,4,5,6]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (16, 6, 1, N'こねる', NULL, 10, 20, 0.0500, 60, NULL, NULL, 1, 0, NULL, NULL, N'[1,2,3,4,5]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (17, 6, 2, N'焼く', NULL, 10, 25, 0.1000, 30, NULL, NULL, 1, 0, NULL, NULL, N'[1,2,3,4,5]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (18, 6, 3, N'包装する', NULL, 5, NULL, 0.1500, 0, NULL, NULL, 1, 0, NULL, NULL, N'[1,2,3,4,5]', 1, NULL, NULL, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
SET IDENTITY_INSERT [M_ProductProcesses] OFF;
SET @IdentityTable = NULL;

-- M_ProductSwitchRules: 22件（製品工程IDで判定）
SET @IdentityTable = N'M_ProductSwitchRules';
SET IDENTITY_INSERT [M_ProductSwitchRules] ON;
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, 1, 10, 10, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 1, 1, 13, 10, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 1, 1, 16, 15, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 1, 4, 10, 10, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 1, 4, 13, 10, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 1, 4, 16, 15, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (7, 1, 7, 10, 10, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (8, 1, 7, 13, 10, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (9, 1, 7, 16, 15, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (10, 1, 10, 1, 10, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (11, 1, 10, 4, 10, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (12, 1, 10, 7, 10, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (13, 1, 10, 16, 15, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (14, 1, 13, 1, 10, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (15, 1, 13, 4, 10, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (16, 1, 13, 7, 10, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (17, 1, 13, 16, 15, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (18, 1, 16, 1, 20, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (19, 1, 16, 4, 20, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (20, 1, 16, 7, 20, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (21, 1, 16, 10, 20, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductSwitchRules] ([ProductSwitchRuleID], [ProductSwitchTimeID], [FromProductProcessID], [ToProductProcessID], [SetupMinutes], [IsForbidden], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (22, 1, 16, 13, 20, 0, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
SET IDENTITY_INSERT [M_ProductSwitchRules] OFF;
SET @IdentityTable = NULL;

-- 作業者マスタの仮データ。オーダーの作業者指定で使用し、計画計算への連携は行わない。
-- M_Workers: 3件
SET @IdentityTable = N'M_Workers';
SET IDENTITY_INSERT [M_Workers] ON;
INSERT INTO [M_Workers] ([WorkerID], [LocationID], [WorkerName], [MaxDailyQuantity], [Remarks], [DeleteFlag]) VALUES (1, 1, N'作業者A（こねる担当）', NULL, N'パン製造デモの作業者', 0);
INSERT INTO [M_Workers] ([WorkerID], [LocationID], [WorkerName], [MaxDailyQuantity], [Remarks], [DeleteFlag]) VALUES (2, 1, N'作業者B（焼く担当）', NULL, N'パン製造デモの作業者', 0);
INSERT INTO [M_Workers] ([WorkerID], [LocationID], [WorkerName], [MaxDailyQuantity], [Remarks], [DeleteFlag]) VALUES (3, 1, N'作業者C（包装担当）', NULL, N'パン製造デモの作業者', 0);
SET IDENTITY_INSERT [M_Workers] OFF;
SET @IdentityTable = NULL;

-- M_WorkerSkillMap: 54件。全工程分を登録し、可18件・不可36件を明示する。
SET @IdentityTable = N'M_WorkerSkillMap';
SET IDENTITY_INSERT [M_WorkerSkillMap] ON;
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (1, 1, 1, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (2, 2, 1, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (3, 3, 1, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (4, 1, 2, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (5, 2, 2, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (6, 3, 2, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (7, 1, 3, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (8, 2, 3, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (9, 3, 3, 1, 1200.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (10, 1, 4, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (11, 2, 4, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (12, 3, 4, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (13, 1, 5, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (14, 2, 5, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (15, 3, 5, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (16, 1, 6, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (17, 2, 6, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (18, 3, 6, 1, 1200.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (19, 1, 7, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (20, 2, 7, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (21, 3, 7, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (22, 1, 8, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (23, 2, 8, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (24, 3, 8, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (25, 1, 9, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (26, 2, 9, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (27, 3, 9, 1, 1200.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (28, 1, 10, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (29, 2, 10, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (30, 3, 10, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (31, 1, 11, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (32, 2, 11, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (33, 3, 11, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (34, 1, 12, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (35, 2, 12, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (36, 3, 12, 1, 1200.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (37, 1, 13, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (38, 2, 13, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (39, 3, 13, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (40, 1, 14, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (41, 2, 14, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (42, 3, 14, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (43, 1, 15, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (44, 2, 15, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (45, 3, 15, 1, 1200.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (46, 1, 16, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (47, 2, 16, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (48, 3, 16, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (49, 1, 17, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (50, 2, 17, 1, 600.000, NULL);
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (51, 3, 17, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (52, 1, 18, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (53, 2, 18, 0, NULL, N'担当外（デモ）');
INSERT INTO [M_WorkerSkillMap] ([WorkerSkillMapID], [WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks]) VALUES (54, 3, 18, 1, 1200.000, NULL);
SET IDENTITY_INSERT [M_WorkerSkillMap] OFF;
SET @IdentityTable = NULL;

-- M_WorkerCalendars: 36件。月～土の06:00～12:00・13:00～18:00、日曜は休み。
SET @IdentityTable = N'M_WorkerCalendars';
SET IDENTITY_INSERT [M_WorkerCalendars] ON;
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, 1, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, 1, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, 2, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 1, 2, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 1, 3, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 1, 3, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (7, 1, 4, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (8, 1, 4, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (9, 1, 5, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (10, 1, 5, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (11, 1, 6, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (12, 1, 6, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (13, 2, 1, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (14, 2, 1, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (15, 2, 2, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (16, 2, 2, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (17, 2, 3, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (18, 2, 3, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (19, 2, 4, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (20, 2, 4, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (21, 2, 5, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (22, 2, 5, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (23, 2, 6, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (24, 2, 6, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (25, 3, 1, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (26, 3, 1, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (27, 3, 2, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (28, 3, 2, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (29, 3, 3, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (30, 3, 3, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (31, 3, 4, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (32, 3, 4, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (33, 3, 5, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (34, 3, 5, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (35, 3, 6, '06:00:00', '12:00:00', N'午前', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_WorkerCalendars] ([WorkerCalendarsID], [WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (36, 3, 6, '13:00:00', '18:00:00', N'午後', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_WorkerCalendars] OFF;
SET @IdentityTable = NULL;

-- M_WorkerCalendarExceptions: 1件。作業者Aの例外休日をWorkerIDで本人へ直接関連付ける。
SET @IdentityTable = N'M_WorkerCalendarExceptions';
SET IDENTITY_INSERT [M_WorkerCalendarExceptions] ON;
INSERT INTO [M_WorkerCalendarExceptions] ([ExceptionID], [WorkerID], [StartAt], [EndAt], [Remark], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, '2026-11-16T10:00:00', '2026-11-16T11:00:00', N'研修（デモ）', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_WorkerCalendarExceptions] OFF;
SET @IdentityTable = NULL;

-- T_Orders: 7件。担当作業者はT_OrderWorkersへ別途登録する。
SET @IdentityTable = N'T_Orders';
SET IDENTITY_INSERT [T_Orders] ON;
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 1, N'WBS-1001', N'食パン 200個（駅前店向け）', 1, 200.000, N'駅前店', '2026-11-16T06:00:00.000000', '2026-11-16T14:00:00.000000', NULL, 10, N'OPEN', NULL, '2026-11-15T15:12:37.000000', N'seed', '2026-11-15T15:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 1, N'WBS-1002', N'バターロール 300個（中央店向け）', 2, 300.000, N'中央店', '2026-11-16T06:00:00.000000', '2026-11-16T16:00:00.000000', NULL, 30, N'OPEN', NULL, '2026-11-15T15:12:37.000000', N'seed', '2026-11-15T15:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 1, N'WBS-1003', N'フランスパン 150個（駅前店向け）', 3, 150.000, N'駅前店', '2026-11-16T06:00:00.000000', '2026-11-16T16:00:00.000000', NULL, 30, N'OPEN', NULL, '2026-11-15T15:12:37.000000', N'seed', '2026-11-15T15:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 1, N'WBS-1004', N'あんパン 180個（中央店向け）', 4, 180.000, N'中央店', '2026-11-16T06:00:00.000000', '2026-11-16T18:00:00.000000', NULL, 20, N'OPEN', NULL, '2026-11-15T15:12:37.000000', N'seed', '2026-11-15T15:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (5, 1, N'WBS-1005', N'メロンパン 120個（北口店向け）', 5, 120.000, N'北口店', '2026-11-16T06:00:00.000000', '2026-11-16T18:00:00.000000', NULL, 30, N'OPEN', NULL, '2026-11-15T15:12:37.000000', N'seed', '2026-11-15T15:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (6, 1, N'WBS-1006', N'くるみパン 160個（北口店向け）', 6, 160.000, N'北口店', '2026-11-16T06:00:00.000000', '2026-11-18T16:00:00.000000', NULL, 40, N'OPEN', NULL, '2026-11-15T15:12:37.000000', N'seed', '2026-11-15T15:12:37.000000', NULL, 0);
INSERT INTO [T_Orders] ([OrderID], [LocationID], [WBSNumber], [OrderName], [ProductID], [Quantity], [CustomerName], [ReleaseAt], [DeadLine], [ShippingDate], [Priority], [Status], [Remarks], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (7, 1, N'WBS-1007', N'食パン 100個（中央店向け）', 1, 100.000, N'中央店', '2026-11-16T06:00:00.000000', '2026-11-17T14:00:00.000000', NULL, 50, N'OPEN', NULL, '2026-11-15T15:12:37.000000', N'seed', '2026-11-15T15:12:37.000000', NULL, 0);
SET IDENTITY_INSERT [T_Orders] OFF;
SET @IdentityTable = NULL;

-- 複数指定・単一指定・未指定の仮データ。IDは自動採番し、監査列は持たない。
INSERT INTO [T_OrderWorkers] ([OrderID], [WorkerID]) VALUES (1, 1), (1, 2), (2, 2), (2, 3), (3, 3);

-- M_ProductProcessResources: 18件
SET @IdentityTable = N'M_ProductProcessResources';
SET IDENTITY_INSERT [M_ProductProcessResources] ON;
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, NULL, 1, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 2, NULL, 2, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 3, NULL, 3, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 4, NULL, 1, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 5, NULL, 2, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 6, NULL, 3, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (7, 7, NULL, 1, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (8, 8, NULL, 2, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (9, 9, NULL, 3, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (10, 10, NULL, 1, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (11, 11, NULL, 2, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (12, 12, NULL, 3, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (13, 13, NULL, 1, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (14, 14, NULL, 2, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (15, 15, NULL, 3, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (16, 16, NULL, 1, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (17, 17, NULL, 2, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
INSERT INTO [M_ProductProcessResources] ([ProductProcessResourceID], [ProductProcessID], [ResourceID], [ResourceGroupID], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (18, 18, NULL, 3, '2026-11-15T15:12:37.000000', NULL, NULL, NULL);
SET IDENTITY_INSERT [M_ProductProcessResources] OFF;
SET @IdentityTable = NULL;

-- T_Tasks: 21件
SET @IdentityTable = N'T_Tasks';
SET IDENTITY_INSERT [T_Tasks] ON;
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (1, 1, 1, N'こねる', 1, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 1, 2, N'焼く', 2, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (3, 1, 3, N'包装する', 3, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (4, 2, 4, N'こねる', 1, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (5, 2, 5, N'焼く', 2, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (6, 2, 6, N'包装する', 3, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (7, 3, 7, N'こねる', 1, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (8, 3, 8, N'焼く', 2, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (9, 3, 9, N'包装する', 3, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (10, 4, 10, N'こねる', 1, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (11, 4, 11, N'焼く', 2, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (12, 4, 12, N'包装する', 3, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (13, 5, 13, N'こねる', 1, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (14, 5, 14, N'焼く', 2, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (15, 5, 15, N'包装する', 3, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (16, 6, 16, N'こねる', 1, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (17, 6, 17, N'焼く', 2, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (18, 6, 18, N'包装する', 3, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (19, 7, 1, N'こねる', 1, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (20, 7, 2, N'焼く', 2, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
INSERT INTO [T_Tasks] ([TaskID], [OrderID], [ProductProcessID], [TaskName], [Sequence], [EarliestStartAt], [DeadlineAt], [Status], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (21, 7, 3, N'包装する', 3, NULL, NULL, N'NOT_STARTED', '2026-11-15T15:12:37.000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [T_Tasks] OFF;
SET @IdentityTable = NULL;

-- T_Plans: 2件。SQL版は比較撮影用の割付・評価値も登録する。Python版も同じ撮影用データを登録する。
-- 2件とも独立した新規計画のため、CopiedFromPlanIDはNULLを登録する。
-- 期間は既存オーダーと同じ現地2026-11-16 06:00から5日間。保存値は日本時間とする。
-- 計画はPlanIDとPlanNameで識別し、製造現場を想定した名前を設定する。
SET @IdentityTable = N'T_Plans';
SET IDENTITY_INSERT [T_Plans] ON;
INSERT INTO [T_Plans] ([PlanID], [LocationID], [PlanName], [Status], [StartAt], [EndAt], [CalculationSettingID], [BasePlanID], [CopiedFromPlanID], [Remarks], [CreatedAt], [CreatedBy]) VALUES (1, 1, N'11月第3週_パン製造計画', N'DRAFT', '2026-11-16T06:00:00', '2026-11-21T06:00:00', 1, NULL, NULL, N'駅前店・中央店・北口店向けの食パン・菓子パンなどの製造計画。', '2026-11-15T15:12:37.000000', N'seed');
INSERT INTO [T_Plans] ([PlanID], [LocationID], [PlanName], [Status], [StartAt], [EndAt], [CalculationSettingID], [BasePlanID], [CopiedFromPlanID], [Remarks], [CreatedAt], [CreatedBy]) VALUES (2, 1, N'11月第3週_パン製造計画v2', N'DRAFT', '2026-11-16T06:00:00', '2026-11-21T06:00:00', 1, NULL, NULL, N'駅前店・中央店・北口店向けの食パン・菓子パンなどの製造計画。', '2026-11-15T15:12:37.000000', N'seed');
SET IDENTITY_INSERT [T_Plans] OFF;
SET @IdentityTable = NULL;

-- 比較撮影用の割付。A=通常計画（18件）、B=見直し計画（21件）。
-- ソルバーの実行結果ではなく、画面説明用に用意したIMPORTデータ。
-- 開始分は2026-11-16 06:00基準。くるみパンは曜日制限に合わせて水曜に配置する。
DECLARE @CompareSlots TABLE (
    PlanID int, TaskID int, ResourceID int, StartMinute int, SetupMinutes int
);
INSERT INTO @CompareSlots (PlanID, TaskID, ResourceID, StartMinute, SetupMinutes) VALUES
    (1,1,1,2880,0), (1,2,3,3000,0), (1,3,5,3090,0),
    (1,4,1,2930,0), (1,5,3,3060,0), (1,6,5,3160,0),
    (1,7,1,2980,0), (1,8,3,3130,0), (1,9,5,3210,0),
    (1,10,1,3040,10), (1,11,3,3300,0), (1,12,5,3390,0),
    (1,13,1,3090,0), (1,14,3,3360,0), (1,15,5,3450,0),
    (1,16,1,3315,15), (1,17,3,3435,0), (1,18,5,3525,0),
    (2,1,1,0,0), (2,2,3,120,0), (2,3,5,210,0),
    (2,4,1,50,0), (2,5,3,180,0), (2,6,5,280,0),
    (2,7,1,100,0), (2,8,3,250,0), (2,9,5,330,0),
    (2,10,2,0,0), (2,11,4,120,0), (2,12,6,210,0),
    (2,13,2,50,0), (2,14,4,180,0), (2,15,6,260,0),
    (2,16,1,2895,15), (2,17,3,3015,0), (2,18,5,3105,0),
    (2,19,1,150,0), (2,20,4,260,0), (2,21,5,390,0);

-- 所要時間は現行の工程候補・オーダー数量から求め、画面のマスタ値と一致させる。
-- WorkerIDはデモ工程番号1/2/3に対応する仮の作業者ID1/2/3。通常の計算結果ではない。
INSERT INTO [T_PlanAssignments]
    ([PlanID], [TaskID], [ResourceID], [WorkerID], [StartAt], [EndAt], [SetupMinutes],
     [IsLocked], [Source], [CreatedAt], [CreatedBy])
SELECT s.PlanID, s.TaskID, s.ResourceID, pr.SequenceNumber,
       DATEADD(minute, s.StartMinute, p.StartAt),
       DATEADD(minute, s.StartMinute + COALESCE(pr.SetupMinutes, 0) + COALESCE(pr.FixedMinutes, 0)
           + CAST(CEILING(o.Quantity * pr.ProcessingMinutes) AS int), p.StartAt),
       s.SetupMinutes, 0, N'IMPORT', '2026-11-15T15:12:37', N'seed'
FROM @CompareSlots s
JOIN [T_Plans] p ON p.PlanID = s.PlanID
JOIN [T_Tasks] t ON t.TaskID = s.TaskID
JOIN [T_Orders] o ON o.OrderID = t.OrderID
JOIN [M_ProductProcesses] pr ON pr.ProductProcessID = t.ProductProcessID;

-- 評価値は割付から集計する。比較画面と同じ7項目を保存する。
-- 負荷率の分母は期間内の拠点勤務時間×設備数。現行seedに拠点の例外休日はない。
;WITH OrderFinishes AS (
    SELECT a.PlanID, o.OrderID, o.DeadLine, MAX(a.EndAt) AS FinishAt
    FROM [T_PlanAssignments] a
    JOIN [T_Tasks] t ON t.TaskID = a.TaskID
    JOIN [T_Orders] o ON o.OrderID = t.OrderID
    GROUP BY a.PlanID, o.OrderID, o.DeadLine
), Lateness AS (
    SELECT PlanID,
           SUM(CASE WHEN FinishAt > DeadLine THEN 1 ELSE 0 END) AS LateOrders,
           SUM(CASE WHEN FinishAt > DeadLine THEN DATEDIFF(minute, DeadLine, FinishAt) ELSE 0 END) AS LateMinutes
    FROM OrderFinishes GROUP BY PlanID
), Working AS (
    SELECT p.PlanID, SUM(DATEDIFF(minute, c.StartTime, c.EndTime)) AS WorkingMinutes
    FROM [T_Plans] p
    CROSS JOIN (VALUES (0),(1),(2),(3),(4)) d(DayOffset)
    JOIN [M_Calendars] c ON c.LocationID = p.LocationID AND c.DeleteFlag = 0
        AND c.DayOfWeek = DATEDIFF(day, '19000107', DATEADD(day, d.DayOffset, p.StartAt)) % 7
    JOIN [M_Resources] r ON r.LocationID = p.LocationID AND r.DeleteFlag = 0
    WHERE p.PlanID IN (1,2)
    GROUP BY p.PlanID
), Metrics AS (
    SELECT p.PlanID, COUNT(a.TaskID) AS ScheduledTasks,
           (SELECT COUNT(*) FROM [T_Tasks]) - COUNT(a.TaskID) AS UnscheduledTasks,
           MAX(DATEDIFF(minute, p.StartAt, a.EndAt)) AS MakespanMinutes,
           SUM(a.SetupMinutes) AS SetupMinutes,
           SUM(DATEDIFF(minute, a.StartAt, a.EndAt)) AS BusyMinutes
    FROM [T_Plans] p JOIN [T_PlanAssignments] a ON a.PlanID = p.PlanID
    WHERE p.PlanID IN (1,2) GROUP BY p.PlanID
)
INSERT INTO [T_PlanKpis] ([PlanID], [KpiKey], [KpiValue])
SELECT m.PlanID, k.KpiKey, k.KpiValue
FROM Metrics m JOIN Lateness l ON l.PlanID = m.PlanID JOIN Working w ON w.PlanID = m.PlanID
CROSS APPLY (VALUES
    (N'納期遅れ', CAST(l.LateOrders AS decimal(18,4))),
    (N'遅れ時間の合計', CAST(l.LateMinutes AS decimal(18,4))),
    (N'段取り時間', CAST(m.SetupMinutes AS decimal(18,4))),
    (N'最終完了', CAST(m.MakespanMinutes AS decimal(18,4))),
    (N'平均負荷率', CAST(ROUND(100.0 * m.BusyMinutes / NULLIF(w.WorkingMinutes,0),1) AS decimal(18,4))),
    (N'割付済みタスク', CAST(m.ScheduledTasks AS decimal(18,4))),
    (N'未割付タスク', CAST(m.UnscheduledTasks AS decimal(18,4)))
) k(KpiKey,KpiValue);


-- センシングのマスタ仮データ。トランザクションデータは追加しない。
-- センシング：M_Calendars 5件。月～金は09:00～17:30の1行とし、土日は稼働に含めない。
SET @IdentityTable = N'M_Calendars';
SET IDENTITY_INSERT [M_Calendars] ON;
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (13, 2, 1, '09:00:00', '17:30:00', N'通常稼働', '2026-11-19T00:00:00.0000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (15, 2, 2, '09:00:00', '17:30:00', N'通常稼働', '2026-11-19T00:00:00.0000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (17, 2, 3, '09:00:00', '17:30:00', N'通常稼働', '2026-11-19T00:00:00.0000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (19, 2, 4, '09:00:00', '17:30:00', N'通常稼働', '2026-11-19T00:00:00.0000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Calendars] ([CalendarID], [LocationID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (21, 2, 5, '09:00:00', '17:30:00', N'通常稼働', '2026-11-19T00:00:00.0000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Calendars] OFF;
SET @IdentityTable = NULL;

-- センシング：M_CalculationSettings 1件（日単位計算モードを既定に設定）
SET @IdentityTable = N'M_CalculationSettings';
SET IDENTITY_INSERT [M_CalculationSettings] ON;
INSERT INTO [M_CalculationSettings] ([CalculationSettingID], [LocationID], [CalculationSettingName], [TimeUnit], [ObjectiveWeightsJSON], [FrozenWindowHours], [IsDefault], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (2, 2, N'センシング・日単位標準', N'DAY', N'{"unscheduled": 100000, "lateness": 1000, "targetLate": 30, "targetEarly": 10, "balance": 50}', 0, 1, '2026-11-24T00:00:00.0000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_CalculationSettings] OFF;
SET @IdentityTable = NULL;

-- センシング：M_ProcessGroups 3件（組立・電気調整・調整検査）
SET @IdentityTable = N'M_ProcessGroups';
SET IDENTITY_INSERT [M_ProcessGroups] ON;
INSERT INTO [M_ProcessGroups] ([ProcessGroupID], [LocationID], [ProcessGroupName], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (1, 2, N'組立', 1, '2026-11-24T00:00:00.0000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_ProcessGroups] ([ProcessGroupID], [LocationID], [ProcessGroupName], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (2, 2, N'電気調整', 2, '2026-11-24T00:00:00.0000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_ProcessGroups] ([ProcessGroupID], [LocationID], [ProcessGroupName], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (3, 2, N'調整検査', 3, '2026-11-24T00:00:00.0000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_ProcessGroups] OFF;
SET @IdentityTable = NULL;

-- センシング：M_Product 5件（部品分譲は作業者の日上限対象外として登録）
SET @IdentityTable = N'M_Product';
SET IDENTITY_INSERT [M_Product] ON;
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [ProductCode], [ExcludeFromDailyCap], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (7, 2, N'LC-450A', N'LC', 0, '2026-11-19T14:48:55.0000000', N'system', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [ProductCode], [ExcludeFromDailyCap], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (8, 2, N'RF-400', N'RF', 0, '2026-11-19T15:01:21.0000000', N'system', '2026-11-19T15:01:54.0000000', N'system', 1);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [ProductCode], [ExcludeFromDailyCap], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (9, 2, N'LD-450及びSセンサ単品', N'LD', 0, '2026-11-19T15:01:56.0000000', N'system', '2026-11-19T15:02:00.0000000', N'system', 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [ProductCode], [ExcludeFromDailyCap], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (10, 2, N'OXZ-740', NULL, 0, '2026-11-19T15:04:23.0000000', N'system', NULL, NULL, 0);
INSERT INTO [M_Product] ([ProductID], [LocationID], [ProductName], [ProductCode], [ExcludeFromDailyCap], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (11, 2, N'部品分譲', NULL, 1, '2026-11-24T00:00:00.0000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Product] OFF;
SET @IdentityTable = NULL;

-- センシング：M_ProductProcesses 18件（工程区分・標準前倒し稼働日数・稼働日間隔を設定、MaxHolidaysAfterはNULL）
SET @IdentityTable = N'M_ProductProcesses';
SET IDENTITY_INSERT [M_ProductProcesses] ON;
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (19, 7, 1, N'ピッキング', 1, NULL, NULL, 3.0000, 0, 0, 5, 1, 0, 0, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 1, NULL, NULL, '2026-11-19T14:49:36.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (20, 7, 2, N'組立', 1, NULL, NULL, 19.0000, 0, NULL, 5, 1, 1, NULL, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T14:50:54.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (21, 7, 3, N'電気調整', 2, NULL, NULL, 20.0000, 0, NULL, 4, 1, 0, NULL, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T14:54:37.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (22, 7, 4, N'エージング', 3, NULL, NULL, 3.0000, 0, NULL, 4, 1, 1, 1, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T14:54:51.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (23, 7, 5, N'ガス校正', 3, NULL, NULL, 41.0000, 0, NULL, 3, 1, 0, 0, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T14:55:17.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (24, 7, 6, N'出荷準備', 3, NULL, NULL, 7.0000, 0, NULL, 3, 1, 1, NULL, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T14:55:34.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (25, 7, 7, N'梱包', 3, NULL, NULL, 0.0000, 0, NULL, 2, 1, 0, NULL, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-24T00:00:00.0000000', N'seed', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (27, 9, 1, N'ピッキング', 1, NULL, NULL, 3.0000, 0, NULL, 5, 1, 1, NULL, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T15:02:26.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (28, 9, 2, N'電気調整', 2, NULL, NULL, 25.0000, 0, NULL, 4, 1, 0, NULL, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T15:02:48.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (29, 9, 3, N'エージング', 3, NULL, NULL, 3.0000, 0, NULL, 4, 1, 1, 1, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T15:03:01.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (30, 9, 4, N'ガス校正', 3, NULL, NULL, 162.0000, 0, NULL, 3, 1, 0, 0, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T15:03:17.0000000', N'system', '2026-11-19T15:03:26.0000000', N'system');
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (31, 9, 5, N'出荷準備', 3, NULL, NULL, 20.0000, 0, NULL, 3, 1, 1, NULL, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T15:03:43.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (32, 9, 6, N'リークテスト', 3, NULL, NULL, 3.0000, 0, NULL, 2, 1, 0, NULL, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T15:04:01.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (33, 10, 1, N'ピッキング', 1, NULL, NULL, 3.0000, 0, NULL, 5, 1, 0, 0, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T15:12:55.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (34, 10, 2, N'組立', 1, NULL, NULL, 30.0000, 0, NULL, 5, 1, 1, NULL, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T15:13:11.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (35, 10, 3, N'電気調整', 2, NULL, NULL, 30.0000, 0, NULL, 4, 1, 0, NULL, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-19T15:14:55.0000000', N'system', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (36, 11, 1, N'ピッキング', 1, NULL, NULL, 0.0000, 0, NULL, 5, 1, 0, 0, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-24T00:00:00.0000000', N'seed', NULL, NULL);
INSERT INTO [M_ProductProcesses] ([ProductProcessID], [ProductID], [SequenceNumber], [ProcessName], [ProcessGroupID], [SetupMinutes], [FixedMinutes], [ProcessingMinutes], [MinLagAfterMin], [MaxLagAfterMin], [StandardOffsetDays], [DurationDays], [MinLagDays], [MaxLagDays], [MaxHolidaysAfter], [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], [WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy]) VALUES (37, 11, 2, N'組立', 1, NULL, NULL, 120.0000, 0, NULL, 5, 1, 0, NULL, NULL, N'[0, 1, 2, 3, 4, 5, 6]', 0, NULL, NULL, '2026-11-24T00:00:00.0000000', N'seed', NULL, NULL);
SET IDENTITY_INSERT [M_ProductProcesses] OFF;
SET @IdentityTable = NULL;

-- センシング：M_ResourceGroups 1件（一般調整検査ライン（5連治具））
SET @IdentityTable = N'M_ResourceGroups';
SET IDENTITY_INSERT [M_ResourceGroups] ON;
INSERT INTO [M_ResourceGroups] ([ResourceGroupID], [LocationID], [GroupName], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (4, 2, N'一般調整検査ライン（5連治具）', 1, '2026-11-26T00:00:00.0000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_ResourceGroups] OFF;
SET @IdentityTable = NULL;

-- センシング：M_Resources 7件（既存2件＋追加5件。Capacity・DailyCapacityQuantityはNULL）
SET @IdentityTable = N'M_Resources';
SET IDENTITY_INSERT [M_Resources] ON;
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [DailyCapacityQuantity], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (7, 2, NULL, N'MFC5連治具', NULL, NULL, NULL, 1, '2026-11-19T14:33:00.0000000', N'system', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [DailyCapacityQuantity], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (8, 2, NULL, N'ガス校正5連治具', NULL, NULL, NULL, 2, '2026-11-19T14:33:13.0000000', N'system', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [DailyCapacityQuantity], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (9, 2, 4, N'５連治具（Aライン）', NULL, NULL, NULL, 3, '2026-11-26T00:00:00.0000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [DailyCapacityQuantity], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (10, 2, 4, N'５連治具（Bライン）', NULL, NULL, NULL, 4, '2026-11-26T00:00:00.0000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [DailyCapacityQuantity], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (11, 2, 4, N'５連治具（Cライン）', NULL, NULL, NULL, 5, '2026-11-26T00:00:00.0000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [DailyCapacityQuantity], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (12, 2, NULL, N'MFC5連治具（Dライン）', NULL, NULL, NULL, 6, '2026-11-26T00:00:00.0000000', N'seed', NULL, NULL, 0);
INSERT INTO [M_Resources] ([ResourceID], [LocationID], [ResourceGroupID], [ResourceName], [Capacity], [DailyCapacityHours], [DailyCapacityQuantity], [SortOrder], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag]) VALUES (13, 2, NULL, N'MFC5連治具（静電気対策ライン）', NULL, NULL, NULL, 7, '2026-11-26T00:00:00.0000000', N'seed', NULL, NULL, 0);
SET IDENTITY_INSERT [M_Resources] OFF;
SET @IdentityTable = NULL;

-- センシング：M_Workers 6件（1日の作業台数上限を設定）
SET @IdentityTable = N'M_Workers';
SET IDENTITY_INSERT [M_Workers] ON;
INSERT INTO [M_Workers] ([WorkerID], [LocationID], [WorkerName], [MaxDailyQuantity], [Remarks], [DeleteFlag]) VALUES (4, 2, N'本間', 15.000, N'組立担当', 0);
INSERT INTO [M_Workers] ([WorkerID], [LocationID], [WorkerName], [MaxDailyQuantity], [Remarks], [DeleteFlag]) VALUES (5, 2, N'岩佐', 20.000, N'電気調整担当', 0);
INSERT INTO [M_Workers] ([WorkerID], [LocationID], [WorkerName], [MaxDailyQuantity], [Remarks], [DeleteFlag]) VALUES (6, 2, N'伴', 10.000, N'調整検査担当', 0);
INSERT INTO [M_Workers] ([WorkerID], [LocationID], [WorkerName], [MaxDailyQuantity], [Remarks], [DeleteFlag]) VALUES (7, 2, N'清川', 10.000, N'調整検査担当', 0);
INSERT INTO [M_Workers] ([WorkerID], [LocationID], [WorkerName], [MaxDailyQuantity], [Remarks], [DeleteFlag]) VALUES (8, 2, N'藤川', 10.000, N'調整検査担当', 0);
INSERT INTO [M_Workers] ([WorkerID], [LocationID], [WorkerName], [MaxDailyQuantity], [Remarks], [DeleteFlag]) VALUES (9, 2, N'上田', 8.000, N'調整検査担当', 0);
SET IDENTITY_INSERT [M_Workers] OFF;
SET @IdentityTable = NULL;

-- センシング：M_WorkerCalendars 30件（6名×月～金。拠点カレンダーの09:00～17:30をコピー）
INSERT INTO [M_WorkerCalendars] ([WorkerID], [DayOfWeek], [StartTime], [EndTime], [WorkName], [CreatedAt], [CreatedBy], [UpdatedAt], [UpdatedBy], [DeleteFlag])
SELECT w.WorkerID, c.DayOfWeek, c.StartTime, c.EndTime, c.WorkName, '2026-11-24T00:00:00.0000000', N'seed', NULL, NULL, 0
FROM [M_Workers] w
JOIN [M_Calendars] c ON c.LocationID = w.LocationID AND c.DeleteFlag = 0
WHERE w.LocationID = 2 AND w.DeleteFlag = 0;

-- センシング：M_WorkerSkillMap 108件（6名×有効18工程。スキルマップに合わせて担当可否を設定）
INSERT INTO [M_WorkerSkillMap] ([WorkerID], [ProductProcessID], [CanExecute], [MaxDailyProcessQuantity], [Remarks])
SELECT
    w.WorkerID,
    pp.ProductProcessID,
    CASE
        WHEN pp.ProcessGroupID = 1 AND w.WorkerID = 4 THEN 1
        WHEN pp.ProcessGroupID = 2 AND w.WorkerID = 5 THEN 1
        WHEN pp.ProcessGroupID = 3 AND pp.ProductID = 7 AND w.WorkerID IN (6, 7, 8, 9) THEN 1
        WHEN pp.ProcessGroupID = 3 AND pp.ProductID = 9 AND w.WorkerID IN (6, 7, 8) THEN 1
        ELSE 0
    END,
    NULL,
    NULL
FROM [M_Workers] w
JOIN [M_Product] p ON p.LocationID = w.LocationID AND p.DeleteFlag = 0
JOIN [M_ProductProcesses] pp ON pp.ProductID = p.ProductID
WHERE w.LocationID = 2 AND w.DeleteFlag = 0;

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
