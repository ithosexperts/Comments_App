/*
  Fresh-install schema matching the verified Test_OperationsDB columns.
  Existing Employee Master and Pending Tasks objects are not created here.
  Run through your normal SQL Server deployment process; do not run against
  Production until the Test API flow has been accepted.
*/
SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.FMS_Comment_Log', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.FMS_Comment_Log
    (
        RecordID BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_FMS_Comment_Log PRIMARY KEY,
        CommentID NVARCHAR(150) NULL,
        FMSRefId NVARCHAR(150) NULL,
        TaskID NVARCHAR(150) NULL,
        StageName NVARCHAR(250) NULL,
        AppID NVARCHAR(150) NULL,
        AppName NVARCHAR(250) NULL,
        [Text] NVARCHAR(MAX) NULL,
        AttachmentURL NVARCHAR(2048) NULL,
        [Timestamp] DATETIME2(0) NOT NULL CONSTRAINT DF_FMS_Comment_Log_Timestamp DEFAULT (SYSDATETIME()),
        Sender NVARCHAR(320) NULL,
        Receiver NVARCHAR(MAX) NULL,
        AttachmentFilename NVARCHAR(512) NULL,
        [Type] NVARCHAR(30) NULL,
        AskID NVARCHAR(150) NULL,
        [Status] NVARCHAR(50) NULL,
        NotificationMessage NVARCHAR(MAX) NULL,
        OpenThread NVARCHAR(150) NULL,
        CompleteStatus NVARCHAR(100) NULL,
        UniqueID NVARCHAR(100) NULL,
        ThreadID NVARCHAR(100) NULL,
        ThreadColor NVARCHAR(20) NULL,
        [Unique] NVARCHAR(150) NULL,
        ExtractedText NVARCHAR(MAX) NULL,
        TimestampInText NVARCHAR(150) NULL
    );
    CREATE INDEX IX_FMS_Comment_Log_CommentID ON dbo.FMS_Comment_Log (CommentID);
    CREATE INDEX IX_FMS_Comment_Log_AskID ON dbo.FMS_Comment_Log (AskID);
    CREATE INDEX IX_FMS_Comment_Log_ThreadID ON dbo.FMS_Comment_Log (ThreadID);
END;
GO

/* Mapping columns as verified in SSMS: FMSRefId, AppID, StageNo, TableName. */
IF OBJECT_ID(N'dbo.FMS_Comment_FMS_Stage_Map', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.FMS_Comment_FMS_Stage_Map
    (
        FMSRefId NVARCHAR(150) NOT NULL,
        AppID NVARCHAR(150) NOT NULL,
        StageNo NVARCHAR(50) NOT NULL,
        TableName NVARCHAR(256) NOT NULL,
        CONSTRAINT PK_FMS_Comment_FMS_Stage_Map
            PRIMARY KEY (TableName, FMSRefId, AppID, StageNo)
    );
END;
GO

/* App-owned case metadata. The creation form is not shown in the Comments UI,
   but these tables preserve optional linked-case references and labels. */
IF OBJECT_ID(N'dbo.FMS_Comment_Case_Map', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.FMS_Comment_Case_Map
    (
        RecordID BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_FMS_Comment_Case_Map PRIMARY KEY,
        CommentID NVARCHAR(150) NULL,
        TaskID NVARCHAR(150) NULL,
        StageName NVARCHAR(250) NULL,
        FMSName NVARCHAR(250) NULL,
        CaseID NVARCHAR(150) NULL,
        CaseURL NVARCHAR(2048) NULL
    );
    CREATE INDEX IX_FMS_Comment_Case_Map_CommentID ON dbo.FMS_Comment_Case_Map (CommentID);
END;
GO

IF OBJECT_ID(N'dbo.FMS_Case_Labels', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.FMS_Case_Labels
    (
        RecordID BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_FMS_Case_Labels PRIMARY KEY,
        Label NVARCHAR(150) NOT NULL
    );
END;
GO

/* Existing source objects: dbo.VM_EmployeeMaster and dbo.Pending_Tasks.
   The app reads VM_EmployeeMaster.EmployeeCode, EmployeeName, OffEmail,
   Active, RoleID, and Department. Pending Tasks/table-specific row columns
   vary by the API contract and are not created or altered here. */
