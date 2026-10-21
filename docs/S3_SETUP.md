# S3 测试环境准备

按顺序完成，每完成一步再继续。本文是操作参考，不表示已经在 AWS 中创建了任何资源。密码、银行卡、验证码和 Access Key 由你在对应页面亲自填写。

## 1. 注册 AWS 账号

打开 [AWS 注册页](https://signin.aws.amazon.com/signup?request_type=register)，填写自己的邮箱和账号名称，验证邮箱后设置密码。按页面完成计划选择、联系方式、付款方式和身份验证。支持计划选择免费选项。账号激活后再继续创建资源；AWS 说明激活通常需要几分钟，有时可能需要 24 小时。[官方注册说明](https://docs.aws.amazon.com/accounts/latest/reference/getting-started.html)

## 2. 保护登录账号

按控制台提示为登录账号设置 MFA。后续用于应用的程序凭证会属于单独的只读 IAM 用户；登录密码与程序凭证用途不同。

## 3. 创建私有测试桶

在 [S3 控制台](https://console.aws.amazon.com/s3/) 选择 **Create bucket**：

- 类型：**General purpose**。
- 区域：建议 **Asia Pacific (Sydney) / ap-southeast-2**，并记下区域代码。
- 名称：小写字母、数字、连字符组成，增加随机后缀，确保名称可用。
- Object Ownership：保留 **ACLs disabled**。
- **Block all public access：保持勾选**。
- 默认加密：选择 **SSE-S3**，即 Amazon S3 托管的密钥。
- 其余设置先保留默认，确认后创建。

保存实际桶名；后面的策略中要使用这个名字。[AWS S3 入门说明](https://docs.aws.amazon.com/AmazonS3/latest/userguide/GetStartedWithS3.html)

## 4. 上传两份测试文件

进入刚创建的桶，选择 **Upload → Add files**，选择项目 `samples` 文件夹内的 `contacts.csv` 和 `contacts.xlsx`，然后上传。这两份文件均为虚构数据，内容一致，各有 8 条记录。

由你的登录账号完成这次上传。应用使用的测试凭证只需要读取权限。

## 5. 创建专用 IAM 用户并配置权限

在 [IAM 控制台](https://console.aws.amazon.com/iam/) 的 **Users → Create user** 创建 `patternworks-s3-reader`，不启用该用户的控制台登录。创建后进入该用户的 **Permissions → Add permissions → Create inline policy**，选择 JSON 编辑器。[创建 IAM 用户](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_users_create.html)、[添加内联策略](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_manage-attach-detach.html)

复制下面的策略，将两个 `YOUR_BUCKET_NAME` 都替换成实际桶名。检查后用名称 `PatternworksTestBucketReadOnly` 保存。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListAndLocateTestBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME"
    },
    {
      "Sid": "ReadTestObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/*"
    }
  ]
}
```

这份策略授予指定测试桶的列举、区域查询和对象读取权限。它本身不授予上传、删除或其他桶访问权限；确认该专用用户没有额外的宽泛策略。应用的连接检查会调用 HeadBucket，它需要 `s3:ListBucket`。[HeadBucket 权限说明](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadBucket.html)

## 6. 生成程序凭证

进入这个 IAM 用户的 **Security credentials → Access keys → Create access key**，按照页面说明选择当前使用场景并创建。你亲自保管 Access Key ID 和 Secret Access Key，将它们直接填到本地应用中。聊天和项目源代码不需要这些密钥。不要为 root 用户创建 Access Key。

## 7. 在应用中连接

Docker 环境启动后打开本地应用，填写实际桶名、Access Key ID、Secret Access Key，以及 `ap-southeast-2`，提交连接。看到任务成功后，应能列出两份测试文件。选择文件后点击 **Import & preview**，由后台解析并显示数据预览。Excel 默认读取第一个工作表，也可输入具体工作表名。已导入的数据集可以在当前浏览器会话中重新打开；读取已生成的预览不需要重新连接 S3。

如果出现 403，先核对桶名、凭证所属用户和上述策略中的两个资源 ARN；如果出现过期或签名错误，核对凭证及临时凭证是否需要 Session Token。无需为应用关闭桶的公网访问阻止设置。
