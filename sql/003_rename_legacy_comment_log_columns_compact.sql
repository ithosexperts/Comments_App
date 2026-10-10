/*
  Optional one-time migration for older databases whose FMS_Comment_Log uses
  spaced column labels. The current verified schema already uses compact labels;
  this script becomes a no-op for those columns. Run in Test_OperationsDB first.
  Execute the full script because GO separates schema-changing batches.
*/
SET NOCOUNT ON;
IF OBJECT_ID(N'dbo.FMS_Comment_Log', N'U') IS NULL
    THROW 50010, 'dbo.FMS_Comment_Log does not exist in the selected database.', 1;
GO

DECLARE @renames TABLE (OldName sysname NOT NULL, NewName sysname NOT NULL);
INSERT INTO @renames (OldName, NewName) VALUES
(N'Comment ID',N'CommentID'), (N'FMS Ref Id',N'FMSRefId'), (N'Task ID',N'TaskID'),
(N'Stage Name',N'StageName'), (N'App ID',N'AppID'), (N'App Name',N'AppName'),
(N'Attachment URL',N'AttachmentURL'), (N'Attachment Filename',N'AttachmentFilename'),
(N'Ask ID',N'AskID'), (N'Notification Message',N'NotificationMessage'),
(N'Open Thread',N'OpenThread'), (N'Complete Status',N'CompleteStatus'),
(N'Unique ID',N'UniqueID'), (N'Thread ID',N'ThreadID'), (N'Thread Color',N'ThreadColor'),
(N'Extracted Text',N'ExtractedText'), (N'Timestamp in text',N'TimestampInText');

DECLARE @old sysname, @new sysname, @cmd nvarchar(max);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT OldName, NewName FROM @renames;
OPEN c;
FETCH NEXT FROM c INTO @old, @new;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF COL_LENGTH(N'dbo.FMS_Comment_Log', @old) IS NOT NULL
       AND COL_LENGTH(N'dbo.FMS_Comment_Log', @new) IS NULL
    BEGIN
        SET @cmd = N'EXEC sys.sp_rename N''dbo.FMS_Comment_Log.['
                 + REPLACE(@old, N'''', N'''''')
                 + N']'', N''' + REPLACE(@new, N'''', N'''''') + N''', N''COLUMN'';';
        EXEC sys.sp_executesql @cmd;
    END;
    FETCH NEXT FROM c INTO @old, @new;
END;
CLOSE c;
DEALLOCATE c;
GO

/* FMS_Comment_Log must not hold TableName or StageNo. Those belong to the map. */
SELECT COLUMN_NAME, ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'FMS_Comment_Log'
ORDER BY ORDINAL_POSITION;
GO
