-- DataBase/queryに配置した、SSMSで手動実行するDB作成SQL。
-- DB名はTONOPS-SCHのままとし、拠点はM_Locationsで管理する。
USE [master];
GO
IF DB_ID(N'TONOPS-SCH') IS NULL
BEGIN
    CREATE DATABASE [TONOPS-SCH];
END;
GO
