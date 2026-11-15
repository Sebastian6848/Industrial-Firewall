# NC-Link 支持核查与改进建议

核查日期：2026-11-15。工业协议插件基于 Gitee plugins 提交 `51dd8652ba66f10b4be6285eb5f82bde9ea9fc8c`。适配器、驱动为工作区提供的源码快照，尚未完成实际设备全链路联调。本次为核查，不调整在线策略。

## 本次修复进展（2026-11-15）

以下正文保留核查时的基线。本次已补主题根前缀、状态通知与发现、显式订阅过滤器和 JSON 审计，操作由 16 类增至 18 类；兼容默认值不自动授权新增操作。修复版驱动已纳入 [contrib/nclink-driver](../contrib/nclink-driver/README.md)，修复语法/运行错误、主题后缀、多设备通道/标签隔离、模型配对和采样格式，并提供明确封装的可选 TCP JSON 接收路径。驱动是 JSON-SCADA 主机组件，不随防火墙 core 安装自动运行。

工业协议单元测试 62 项通过；Suricata 离线扩展回放 52 个场景通过，包括 13 个新增 NC-Link 场景。驱动 9 项回归测试通过，其中使用真实本地 MQTT broker 和 TCP 套接字，数据库使用内存替身。硬件可信、国密握手、在线 IPS、真实 MongoDB/机床和对象级写值防火墙仍需分别实现或验收，不能视为本轮已经完成。

## 当前支持程度

当前是 **NC-Link over MQTT 的业务主题白名单和审计**，还不是完整 NC-Link JSON 语义防火墙，也不是经过硬件证明的 NC-Link 可信接入系统。

| 能力 | 当前结果 |
| --- | --- |
| 明文 MQTT 承载的 NC-Link | 使用 Suricata MQTT 解析结果匹配业务主题 |
| 业务类型 | 16 类：注册、版本探测、模型查询/设置、数据查询/设置、采样、采样注册/注销、方法调用/控制/状态/结果、事件注册/注销/上报 |
| 范围限制 | 源/目标地址、目标端口、主题中的设备和可选客户端/通道后缀 |
| 消息与业务方向 | 可选 PUBLISH、SUBSCRIBE 或两者；请求/响应指主题语义，匹配方向为客户端到 broker |
| 默认拒绝 | 对配置范围内选定的 PUBLISH/SUBSCRIBE 拒绝未授权主题；实际丢包要求 IPS |
| 注册身份 | `Register/Request` 是公共主题，尚不按其中 `cli_uuid` 做设备授权 |
| 业务 JSON | 不校验 `guid`、`values[].id`、写值、模型内容或方法参数；少量字段只用于审计 |
| 会话约束 | 不验证注册→模型→采样状态、不做请求响应关联或应用层重放判定 |
| 加密链路 | 未实现 TLS/GMTLS 解密后的检查链路，不能检查密文主题和 JSON |
| 其他承载 | 尚无独立 TCP JSON、MQTT over WebSocket 的 NC-Link 检查实现 |
| 硬件可信接入 | 未对接 TPCM、远程证明、硬件密钥或可信状态驱动的准入 |

审核机 Suricata 正在运行，在线使用 LAN IDS/PCAP。已有规则中的 `drop` 不代表该拓扑已经实现在线阻断。工业协议后台现有 56 项单元测试本轮全部通过；这不替代真实适配器和驱动互通、在线 IPS 或加密链路验收。

工作区 `plugins/net/nclink-proxy/` 另有未跟踪的 MQTT 观察代理代码：它解码、记录并原样转发，解析失败或观察缓冲超限仍继续转发，不能当作白名单执行点。审核机未安装此服务。本次保留该目录原状，不纳入现有功能计数。

## 为什么现在只有 MQTT

提供的 ModBus、MTConnect、OPC-UA 适配器通过 MQTT 发布 NC-Link 消息。配置里的 `tcp://...:1883` 是 MQTT 客户端的连接地址，不能据此认定业务是独立 TCP JSON 协议。南向 Modbus/OPC UA/MTConnect 是适配器与设备之间的协议，不是三个新的 NC-Link 网络承载。

驱动 `index.js:23,107` 实际导入并启动 `mqtt-client.js`。虽然保留 `tcp-server.js` 和 TCP 测试客户端，但 TCP 调用 `routerFn(pdu)`，当前路由接口是 `route(topic,pdu)`，两者尚不匹配。因此“存在 TCP 文件”不等于已具备可用的双传输驱动。若项目确实使用 TCP JSON，应先确定消息类型字段和分帧约定，不能依赖 `@id` 前缀猜测业务。

## 核实的适配缺口

1. **主题根前缀**：驱动 `mqtt-client.js` 支持 `topicRoot`，当前防火墙只识别裸主题。`Sample/dev01/channel0` 能匹配，而 `nclink/Sample/dev01/channel0` 不能。应增加显式根前缀配置，默认空值兼容现有规则，不通过去除任意首段进行模糊识别。
2. **状态通知与发现**：驱动订阅和处理 `Notify`，现有 16 类白名单未包含 `Notify/State/...`；`Discovery/...` 也未纳入。当前默认拒绝可能阻断这些消息。主题格式应按实际源码、抓包和约定逐项补齐，不默认允许整个命名空间。
3. **通配订阅冲突**：驱动订阅 `Register/#`、`Probe/#`、`Sample/#` 等。当 NC-Link 规则选择检查 SUBSCRIBE 且默认拒绝时，这些过滤器不匹配现有精确设备主题规则。应提供适配器/驱动两类订阅模板与 broker ACL；不能为了驱动互通而无条件放开 `#`。
4. **完整后缀不代表端到端互通**：驱动 `handlers/probe.js:348` 发布 `Probe/Query/Request/<device>/<ex_cid>`；ModBus 与 MTConnect 的 `CallBack.cpp` 订阅逻辑只拼接 `<prefix><device>`，不订阅任意后缀。OPC-UA 又把后缀用于节点标识。防火墙当前允许一或两段后缀，只说明匹配能力，不能解决两端语义差异。需要确定设备、终端、节点、通道的字段含义和兼容配置。
5. **JSON 身份和审计缺口**：适配器使用 `@id`、`cli_uuid`、`guid`、`dev_uuid`、`id` 等字段。当前审计未提取常见 `@id`；包含 `@id/guid/id/data` 的采样消息返回空业务审计字段。请求主题中的设备也未与报文身份、连接身份绑定，公共注册主题不能限制报文里的设备。
6. **写操作缺少对象和值校验**：ModBus `SetRequest.cpp` 接收 `values[].id` 和 `params.value` 并调用底层写线圈/寄存器；`ProbeSetRequest.cpp` 写模型文件。主题授权后，防火墙不会限制数据项、数值范围或模型变更。建议对写值、模型设置、方法调用分别授权，而不是一个写权限覆盖所有操作。
7. **采样格式差异**：驱动 `handlers/sample.js` 读取 `guid/id/data`，期望二维数组；MTConnect 适配器发送 `dev_uuid/id/data`，其中每行是含 `data` 的对象，并使用 `beginTime`。驱动仅把 `cli_uuid` 归一为 `guid`，没有处理此种差异。应定义明确的兼容配置，核对身份、行列数、类型、时间与速率；不能静默丢弃无法解释的列。
8. **多设备隔离**：驱动 `handlers/probe.js:321` 以通道 ID 单独索引 `sampleChannels`，采样处理同样按通道 ID 查询。不同设备使用相同通道名可能覆盖，应改为设备与通道联合索引并核对来源身份。

## 驱动本身的阻塞问题

对工作区 13 个 JavaScript 文件执行 Node.js `--check`，10 个通过，3 个失败：

- `router.js`：`parseTopic` 缺少闭合花括号，报 `Unexpected end of input`。
- `handlers/register.js:73`：返回对象的 `topic` 与 `payload` 之间缺少逗号。
- `handlers/probe.js:124`：同类缺少逗号。

此外，注册处理对缺失身份返回 OK；驱动的 Query 转发为占位拒绝实现，Set/Method 也未具备完整下行闭环。代码检查只能说明提供的源码现状，不能据此推断其他现场版本也存在相同错误。本轮未修改这些参考源码。

## 可信与国密要求

适配器目录的 `NC-Link代理器/安全可信NC-Link代理器测试方案.docx` 描述了用户名/口令、单向/双向证书、按用户及主题的读写授权、GMTLS V1.1 / ECC-SM4-SM3、硬件密钥保护、TPCM 静态/动态度量及可信互操作。这些是参考项目的测试要求或记录，不能计为本防火墙已通过的能力。

本防火墙目前的软件完整性基线不等同于 TPCM 远程证明。普通 TLS 支持也不等同于支持测试方案中的国密双证书套件。需要明确证书体系、目标密码库/设备接口、FreeBSD 兼容性，并用实际握手、失败拒绝、可信状态变化和断线恢复测试验收。

## 建议落地顺序

1. **互通与可观测性**：修复参考驱动的启动问题；补主题根前缀、Notify/Discovery、JSON 字段审计、明确的主题后缀兼容配置和设备/通道索引；建立注册→探测→模型→采样的真实链路测试。
2. **业务白名单执行**：在受控的 MQTT broker 插件或专用应用代理中，完整组装并解析消息后、在转发前校验身份、数据项、读写权限、值域、模型和方法参数；明确报文大小、嵌套、批量项数、超时及失败拒绝策略。现有观察代理需要改造和独立验收，不能直接启用充当执行点。
3. **会话与抗重放**：注册状态、请求响应 `@id` 配对、模型版本、通道归属与采样频率；结合 QoS DUP/重传语义设计重复请求处理，不能把正常 MQTT 重投递一律认定为攻击。
4. **加密与可信准入**：明确 TLS/GMTLS 终止和再加密边界，结合 broker 身份及 ACL 保持设备授权；再对接 TPCM/远程证明与密钥硬件。跨不同网络路径的策略应保持一致，避免加密端口形成旁路。
5. **按真实需求增加承载**：若交付拓扑确实需要，再增加独立 TCP JSON，随后评估 WebSocket；复用业务模型校验与审计层，为各承载分别验证分帧、重连、超限和拒绝行为。

## 验收重点

合法注册、模型查询与采样应通过；同 IP 冒用其他设备、主题与 JSON 身份冲突、越权数据项/超限写值、未经授权的模型更改、跨设备同名通道、未知主题、通配订阅越权、错误采样布局、非法 JSON 和过大/过深报文应有明确处置及审计。拆分/合并报文、连接复用、正常重传、证书过期/不受信、服务重启和主备切换需分别验证。

## 依据

- 插件源码：`plugins/security/icsguard/src/opnsense/scripts/indproto/generators/nclink.py`、`nclink_semantics.py`、`log_query.py`。
- 本地适配器：`nc-link-adapter-master/nc-link-adapter-master/` 下 ModBus、MTConnect、OPC-UA 源码及可信代理器测试方案。
- 本地驱动：`nclink-driver-main/nclink-driver-main/` 下启动入口、MQTT/TCP 传输、路由和业务处理代码。
- [Suricata 8.0.5 MQTT 关键字](https://docs.suricata.io/en/suricata-8.0.5/rules/mqtt-keywords.html)：提供主题、消息体等匹配原语，不等于本项目已经实现 NC-Link 对象级业务校验。
- [OASIS MQTT 5.0](https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html)：主题与应用负载分离，具体负载格式由应用约定。
