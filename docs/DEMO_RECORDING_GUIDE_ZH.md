# Patternworks 录屏步骤

配套讲稿：[英文逐段讲稿](DEMO_SCRIPT_EN.md)。建议剪辑后约 6–7 分钟；这是建议，原始题目没有规定具体时长。操作稍慢可以控制在约 8 分钟，不必赶读。

## 对照原始任务

已重新读取[原始考核 PDF](https://drive.google.com/file/d/17dskAyCYFGbcwX_7yo-VHqpEl14zeciK/view)。原文对视频明确要求：演示应用实际运行，包括用户输入凭证连接 S3，以及异步任务执行完成，最后将视频嵌入 README。其余内容是为了用短视频覆盖项目的主要考核点。

| 考核点 | 视频段落 | 录到的实际证据 |
| --- | --- | --- |
| 自有 S3 凭证、文件浏览 | 02–03 | 用户填写遮蔽的密钥输入框，连接后出现真实文件列表 |
| CSV/Excel 支持 | 03 | Excel 自动读取工作表，再实际导入 60 行 CSV |
| 自然语言、目标多列、替换值 | 05 | Email 和 Notes，固定英文描述，独立替换值 |
| 校验、预览、Redis 缓存 | 05–06 | Rule details、前后值比较、修改后必须重新预览、实际 cache-hit 提示 |
| 异步处理、状态、完成结果 | 03、07 | 真实进度；至少一段从提交到完成连续保留 |
| 分页结果 | 04 | Next 后行号 26，再回到第一页 |
| 两种额外 LLM 转换 | 08–09 | 日期和分类均实际 Preview、Apply，展示新增结果及状态列 |
| 可用交付物与规模证据 | 10、12 | 实际下载的 CSV，GitHub、README、绿色检查和已有百万行报告 |

版本星系是辅助展示，用约 15–20 秒即可。删除、恢复、保留策略和精确文本替换不属于这段短视频的必拍内容。取消、失败重试可放在可选附录。

## 录制前准备

1. 在 Safari 打开[公网应用](https://patternworks.32-237-44-97.nip.io/)，先完成 reviewer 访问登录，录制中不展示该密码。关闭网页自动翻译，保持英文界面，浏览器缩放约 100%，只录应用窗口并打开勿扰。
2. 在 AWS 的 S3 控制台中，用有上传权限的账号打开测试桶 `patternworks-test-20261017-k7m3`。在 Objects 中选 Upload → Add files，上传项目 `samples/demo-contacts-60.csv`，确认成功。录屏使用的 S3 只读密钥不能负责上传。无需修改桶权限或重建服务器。
3. 确认桶里仍有原来的 `contacts.xlsx`，工作表为 `Contacts`。如果没有 Excel 示例，可先只做 CSV 主流程，并把英文第 03 段的工作表一句删去；不要口述未展示的动作。
4. 将桶名、区域和下方输入文本放到录屏范围之外的备忘录。AWS region 使用 `ap-southeast-2`。密钥从自己的安全保存位置输入，不写到讲稿、聊天、文件名或剪贴板历史展示中。
5. 打开 Sources。如果已连接，用 **Disconnect S3** 回到连接表单；它只断开 S3 连接，不删除已导入的数据。保持同一个浏览器会话，不清除网站 cookie。
6. 另备两个浏览器标签：私有 [GitHub 仓库](https://github.com/LYQ1657645/patternworks) 和 [百万行报告](https://github.com/LYQ1657645/patternworks/blob/main/docs/ASYNC_WORKSHEETS_AND_REGEX_ACCEPTANCE_2026-10-20.md)。找到报告里的性能表；不要在录制时翻服务器日志或打开环境文件。
7. 先试读英文讲稿，再录画面。可以分段录、后期配音；任务等待时间可以剪短并标注 `Waiting time shortened`。至少保留一次真实 Apply 从提交到完成的连续画面。不要把另一条任务的成功画面接成当前任务的结果。
8. Mac 可以用 **Command + Shift + 5** 打开录屏工具，选“录制所选部分”，框住应用和网址；在“选项”里选择麦克风。先录 10 秒确认画面清晰、声音可听，再正式录制。讲稿放到录制区域之外；停止时使用菜单栏的停止按钮。也可以先录操作，再按编号逐段配音。

60 行文件全部为虚构数据，具有 6 列、空邮箱、无效邮箱、多邮箱备注、逗号备注、8 种日期值和国家别名。它让分页可见，不是百万行性能样本。新文件已在本地生成并通过应用的真实 CSV 解析器检查；实际 S3 导入需要录制前由你完成上传和预演。

## 按段录制

每段对应英文讲稿同编号段落。时间是剪辑目标，不是任务的性能承诺。

### 01 开场，约 20 秒

- **展示**：公网地址、Patternworks 标识、Sources 连接表单。
- **操作**：鼠标停稳，读英文第 01 段。不要先打开开发工具或解释星系技术。
- **目的**：让评审立即知道这是数据转换应用，以及本次会完成什么流程。

### 02 输入自己的凭证连接，约 30 秒

1. Bucket name 填 `patternworks-test-20261017-k7m3`。
2. AWS region 填 `ap-southeast-2`。
3. 输入自己的只读 Access Key ID 和 Secret Access Key。两个字段保持遮蔽，不点显示密码，不打开凭证文件。若自动填充面板会泄露内容，先关闭面板再继续录制。
4. 点击 **Connect bucket**，录到连接成功、凭证表单被文件列表替代。

**应看到**：Source files 和测试桶里的文件。读第 02 段。不能只展示一个录制前就已连接的页面来代替本段。

### 03 浏览文件并异步导入，约 30–45 秒

1. 先点 `contacts.xlsx`，等工作表读取成功，展示下拉框默认 `Contacts`。这一步只读取工作表列表，没有导入数据。
2. 再点 `demo-contacts-60.csv`。CSV 不需要选工作表。
3. 点击 **Import file**，展示按钮旁的实际进度，等成功。
4. 如果自动弹出数据，直接继续；如果只出现成功提示，点 **View result**。

**应看到**：文件名、`60 rows`、`6 columns`、数据预览。读第 03 段。若下拉框显示的真实工作表名称不同，按实际页面说，不强行使用文字示例。

### 04 原始数据和分页，约 20 秒

1. 展示 Email、JoinDate、Country、Notes，指出日期格式和国家写法不同。
2. 指到第 4 行空邮箱、第 6 行 `not-an-email`，第 5 行备注有两个邮箱。
3. 滚到表格底部，点击 **Next**，让评审看到第二页从行号 **26** 开始；点击 **Previous** 回到第一页。
4. 点击预览右上 **Transform**。

**应看到**：原始数据仍未改变。读第 04 段。旧的 8 行示例没有下一页按钮；若误用了旧文件，回到 Sources 导入 60 行文件，不要把滚动说成分页。

### 05 生成规则并检查预览，约 40 秒

1. 选择 **Regex**。
2. 只勾选 **Email**、**Notes**，确认没有勾选 ID 或其他列。
3. `What to match` 填入：

   ```text
   Find email addresses.
   ```

4. `Replacement text` 填 `[REDACTED]`，点击 **Generate**，等待预览就绪。
5. 展开 **Rule details**，展示实际生成的表达式和 `Syntax and safety checks passed`。
6. 展开 **Compare sample values**；先看 Email，再看 Notes。或用预览的 Column 下拉框切换两列。

**应看到**：邮箱被替换的前后对比，源数据尚未生成新的处理结果。读第 05 段。正则可能因模型或缓存不同而变化，不需要逐字符念，也不要承诺任意邮箱格式都支持。

### 06 防止旧预览执行，并展示缓存，约 30 秒

1. 把替换值从 `[REDACTED]` 改为 `[EMAIL]`，保持描述完全不变。
2. 指一下 **Apply** 不可用，以及需要新预览的提示。
3. 点击 **Update preview**，等成功。
4. 再展开 **Rule details**，确认出现 `Reused a cached rule without a model call.` 后再读第 06 段。

**应看到**：新的替换值出现在预览中，并有实际缓存命中提示。若没有 cache-hit 提示，只说明重新生成预览，不读“this request used the cache”这句；在同一会话、缓存有效期内重复相同描述再检查。

### 07 Apply，展示异步执行与结果，约 40–60 秒

1. 点击 **Apply**。
2. 打开顶部 **Tasks**，找到本次 Apply regex 任务，展示进度；任务较快时，直接展示实际完成状态，不伪造中间状态。
3. 至少将这次真实 Apply 的提交到完成连续保留。等待时读第 07 段前半段即可。
4. 成功后在 Tasks 中点 **View data**；或关闭 Tasks，点 **View result**。
5. 检查 Email 和 Notes 的 `[EMAIL]`，第 4 行仍为空，第 6 行仍为 `not-an-email`，其他列未被替换。
6. 可展开 **Results by column** 看两列的实际统计。然后点击 **Transform**，继续处理这个正则结果版本。

**关键**：后续日期操作必须基于刚生成的正则结果，而不是回到原始版本。读第 07 段剩余内容。

### 08 额外转换一，日期标准化，约 40–50 秒

1. 打开 **Dates and categories**。
2. `Transformation` 选择 **Normalize dates**，`Column` 选择 **JoinDate**。
3. `Ambiguous dates` 保持 **Leave uncertain dates blank**。本例没有必须猜测日/月顺序的值。
4. 勾选 **Allow OpenAI to process the selected values for preview and Apply**，点击 **Preview**。
5. 展示 `03 Oct 2026` → `2026-10-03`、`2026/10/02` → `2026-10-02`。
6. 点击 **Apply**，成功后 **View result**。点 **Show result columns** 或将表格横向滚到右端。
7. 展示 `JoinDate_normalized` 和 `JoinDate_normalized_status`，再点 **Transform** 继续这个 8 列版本。

**应看到**：60 行、8 列；原始 JoinDate 保留，标准日期写入新列。读第 08 段。不要把原始日期列没改误判为失败。

### 09 额外转换二，国家分类，约 40–50 秒

1. 在 **Dates and categories** 中，将 `Transformation` 改为 **Classify values**。
2. 重新选择 `Column` 为 **Country**。切换转换类型后列选择会清空，这是正常的。
3. `Categories` 每行一个，填入：

   ```text
   United States
   Australia
   Other
   ```

4. `When unsure` 选择 **Other**。
5. 展开 **Additional instructions**，填入：

   ```text
   Map USA, U.S., and United States to United States. Map AU, AUS, and Australia to Australia. Use Other for anything else.
   ```

6. 勾选允许处理选中值的复选框；若已经勾选，保持即可。
7. 点击 **Preview**，检查 USA/U.S. 的结果为 United States，AU/AUS 为 Australia；再点击 **Apply**。
8. 成功后 **View result**，点 **Show result columns**，展示 `Country_category` 和 `Country_category_status`。

**应看到**：60 行、10 列，先前的邮箱替换和日期结果仍在。读第 09 段。如果某个值被标记需要检查，展示并解释实际状态，不把它说成已成功分类。

### 10 实际下载 CSV，约 20–30 秒

1. 确认当前是最终 **60 行、10 列**的版本。
2. 点击 **Export CSV**，等按钮变成 **Download CSV**，再点击下载。
3. 打开刚下载的文件。文件名是 `patternworks-<数据集ID>.csv`，不是源 S3 文件名；按最新下载时间识别。
4. 在 Numbers/Excel 中检查列和最后一条 ID 60。表头占一行，所以完整文件是 **61 行含表头**。CSV 读取器可能把空格、日期、长数字自动格式化，录制前选择按文本导入。

**应看到**：Email 和 Notes 为预期替换值，新增日期/分类及其状态列，所有记录均在。读第 10 段。空值在网页显示为 null，导出为 CSV 空单元格是正常行为。

### 11 版本与任务，约 15–20 秒

1. 返回网页并关闭数据弹窗，查看该文件的星系。点星系拉近，简短展示版本间的连接。
2. 点原始版本（Original）查看原邮箱，说明原始版本保留；不要继续从原始版本生成额外结果。
3. 关闭预览，打开 **Tasks**，展示刚刚完成的导入、Generate、Apply 和导出记录。

读第 11 段。星系中的 V1/V2 编号不需要逐个解释；重复内容可能只显示一个星球，完整执行记录由 Tasks 保留。

### 12 架构、规模证据与结束，约 35–45 秒

1. 切到 GitHub README，展示公网地址、Docker Compose 启动命令和 Architecture 图。不实际重启服务器，不展开 `.env.local` 或 `.env.production`。
2. 如果有时间，展示本次绿色 [GitHub Actions](https://github.com/LYQ1657645/patternworks/actions/runs/39555316894)。
3. 打开已有百万行报告的性能表，展示 CSV import 81.139 s、Regex replacement 73.848 s、cached date 48.177 s、cached classification 51.384 s。
4. 读第 12 段，用约数即可。说明这是另一份百万行合成 CSV 的单机测试，日期/分类使用缓存映射，排除 S3 传输和实时模型延迟；不能把当前的 60 行现场操作称为百万行实测。

## 可选附录：取消与重试

主片无需为了展示错误而破坏工作中的主流程。如需额外覆盖可靠性，主流程录完后再单独录约 30–45 秒。

1. 从一个可用版本发起测试转换，任务处于 Waiting/In progress 时，在 **Tasks** 里点 **Cancel**。
2. 等状态确实为 **Cancelled** 后再说取消成功。若任务抢先完成，不称为取消成功；另录一次。
3. 选中这条已取消任务，只有实际出现 **Retry** 时才点击。完成后展示旧任务仍为 Cancelled、新任务为 Complete。
4. 使用英文讲稿的 optional cancellation 段落。真正 FAILED 的重试只在有实际可重试错误、且已解决原因时展示，不故意填错 Access Key 或断开生产 Redis。

## 录完自查与后续交付

- [ ] 看到用户实际输入遮蔽的凭证并连接成功，没有密码、密钥或凭证管理面板泄露。
- [ ] 看到一个真实任务从提交、进度到完成，并打开对应结果。
- [ ] 正则在 Email 和 Notes 同时生效；Generate 与 Apply 的区别清楚。
- [ ] 缓存口述与实际提示一致；日期和分类均录到 Apply 的真实结果。
- [ ] 分页操作显示从行 1 到行 26，而不是单纯滚动。
- [ ] 最终下载是本次 60 行、10 列版本；源数据没有被覆盖。
- [ ] 百万行数据的说法与现有报告范围一致，没有把单机称为多机器集群。
- [ ] 所有剪掉或加速的等待都没有改变任务的真实性；声音与操作对应。

原始视频可以先保存在本地。选好最终视频托管链接后，再把实际视频或可点击封面嵌入 README；目前 README 保持“待录制”，不预填不存在的链接。私有 GitHub 仓库也要在交付时给评审添加访问权限。

本次准备核对了原始题目、当前组件的按钮与状态逻辑，以及已有公网/规模验收记录；没有为了写讲稿再次提交模型任务、运行百万行测试、上传 S3 文件或更改公网服务。
