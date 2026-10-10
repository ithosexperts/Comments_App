/*
  Upgrade an existing mapping table so each context is keyed by:
  TableName + FMSRefId + AppID + StageNo.
  This script is idempotent for the final compact schema. Existing rows are kept.
  Run on Test_OperationsDB first. Execute the whole script; GO batches are required.
*/
SET NOCOUNT ON;
IF OBJECT_ID(N'dbo.FMS_Comment_FMS_Stage_Map', N'U') IS NULL
    THROW 50001, 'dbo.FMS_Comment_FMS_Stage_Map does not exist in the selected database.', 1;
GO

/* Normalize legacy mapping-column names in separate batches. */
IF COL_LENGTH(N'dbo.FMS_Comment_FMS_Stage_Map', N'FMSRefId') IS NULL
   AND COL_LENGTH(N'dbo.FMS_Comment_FMS_Stage_Map', N'FMS Ref Id') IS NOT NULL
    EXEC sys.sp_rename N'dbo.FMS_Comment_FMS_Stage_Map.[FMS Ref Id]', N'FMSRefId', N'COLUMN';
GO
IF COL_LENGTH(N'dbo.FMS_Comment_FMS_Stage_Map', N'AppID') IS NULL
   AND COL_LENGTH(N'dbo.FMS_Comment_FMS_Stage_Map', N'App ID') IS NOT NULL
    EXEC sys.sp_rename N'dbo.FMS_Comment_FMS_Stage_Map.[App ID]', N'AppID', N'COLUMN';
GO
IF COL_LENGTH(N'dbo.FMS_Comment_FMS_Stage_Map', N'StageNo') IS NULL
   AND COL_LENGTH(N'dbo.FMS_Comment_FMS_Stage_Map', N'Stage No') IS NOT NULL
    EXEC sys.sp_rename N'dbo.FMS_Comment_FMS_Stage_Map.[Stage No]', N'StageNo', N'COLUMN';
GO
IF COL_LENGTH(N'dbo.FMS_Comment_FMS_Stage_Map', N'TableName') IS NULL
BEGIN
    IF COL_LENGTH(N'dbo.FMS_Comment_FMS_Stage_Map', N'Table Name') IS NOT NULL
        EXEC sys.sp_rename N'dbo.FMS_Comment_FMS_Stage_Map.[Table Name]', N'TableName', N'COLUMN';
    ELSE
        ALTER TABLE dbo.FMS_Comment_FMS_Stage_Map ADD TableName NVARCHAR(256) NULL;
END;
GO

IF COL_LENGTH(N'dbo.FMS_Comment_FMS_Stage_Map', N'FMSRefId') IS NULL
    THROW 50002, 'FMSRefId mapping column missing; review the existing table schema.', 1;
IF COL_LENGTH(N'dbo.FMS_Comment_FMS_Stage_Map', N'AppID') IS NULL
    THROW 50003, 'AppID mapping column missing; review the existing table schema.', 1;
IF COL_LENGTH(N'dbo.FMS_Comment_FMS_Stage_Map', N'StageNo') IS NULL
    THROW 50004, 'StageNo mapping column missing; review the existing table schema.', 1;
GO

UPDATE dbo.FMS_Comment_FMS_Stage_Map SET TableName = N'' WHERE TableName IS NULL;
GO
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.FMS_Comment_FMS_Stage_Map')
      AND name = N'TableName' AND is_nullable = 1
)
    ALTER TABLE dbo.FMS_Comment_FMS_Stage_Map ALTER COLUMN TableName NVARCHAR(256) NOT NULL;
GO

DECLARE @pk sysname;
DECLARE @pk_ok bit = 0;
DECLARE @drop_sql nvarchar(max);
SELECT @pk = kc.name
FROM sys.key_constraints AS kc
WHERE kc.parent_object_id = OBJECT_ID(N'dbo.FMS_Comment_FMS_Stage_Map') AND kc.type = N'PK';

IF @pk IS NOT NULL AND EXISTS (
    SELECT 1
    FROM sys.key_constraints AS kc
    WHERE kc.parent_object_id = OBJECT_ID(N'dbo.FMS_Comment_FMS_Stage_Map')
      AND kc.type = N'PK'
      AND (SELECT COUNT(*) FROM sys.index_columns ic
           WHERE ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id AND ic.key_ordinal > 0) = 4
      AND NOT EXISTS (
          SELECT wanted.key_ordinal, wanted.column_name
          FROM (VALUES (1,N'TableName'),(2,N'FMSRefId'),(3,N'AppID'),(4,N'StageNo')) AS wanted(key_ordinal,column_name)
          WHERE NOT EXISTS (
              SELECT 1 FROM sys.index_columns ic
              JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
              WHERE ic.object_id=kc.parent_object_id AND ic.index_id=kc.unique_index_id
                AND ic.key_ordinal=wanted.key_ordinal AND c.name=wanted.column_name
          )
      )
)
    SET @pk_ok = 1;

IF @pk IS NOT NULL AND @pk_ok = 0
BEGIN
    SET @drop_sql = N'ALTER TABLE dbo.FMS_Comment_FMS_Stage_Map DROP CONSTRAINT ['
                  + REPLACE(@pk, N']', N']]') + N']';
    EXEC sys.sp_executesql @drop_sql;
END;

IF @pk_ok = 0
    ALTER TABLE dbo.FMS_Comment_FMS_Stage_Map
        ADD CONSTRAINT PK_FMS_Comment_FMS_Stage_Map PRIMARY KEY (TableName, FMSRefId, AppID, StageNo);
GO

SELECT TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'FMS_Comment_FMS_Stage_Map'
ORDER BY ORDINAL_POSITION;
GO
