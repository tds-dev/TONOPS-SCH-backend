-- DataBase/queryに配置した、SSMSで手動実行するDB作成SQL。
-- DB名はTONOPS-SCHのままとし、拠点はM_Locationsで管理する。
-- 拠点の週次勤務はM_Calendars、休日・停止はM_CalendarExceptionsで管理する。
-- DB作成後はschema_sqlserver.sql、seed_demo_sqlserver.sqlの順で、製品・工程・実行候補の3階層を作成・登録する。
USE [master];
GO
IF DB_ID(N'TONOPS-SCH') IS NULL
BEGIN
    CREATE DATABASE [TONOPS-SCH];
END;
GO
