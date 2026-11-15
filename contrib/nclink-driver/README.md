# NC-Link 驱动修复版

本目录是工作区提供的 JSON-SCADA NC-Link 驱动的维护版本，随 Gitee core 仓库托管。MongoDB 与 MQTT 依赖固定在 `package-lock.json`；不把数据库配置、凭据或运行日志纳入源码。

修复了路由和响应对象的语法错误、版本处理中的未定义变量及重复响应、消息解析崩溃、模型响应未配对、主题与报文身份冲突，以及多设备同名通道/数据项相互覆盖。默认适配已有 ModBus/MTConnect 的设备级精确主题，不自动扩大已有防火墙权限。

## 安装与测试

需要 Node.js 20 或更新版本，在 JSON-SCADA 主机使用此目录替换原驱动目录，并保留外部 `json-scada.json`：

```sh
npm ci --omit=dev
node index.js 1 1 /path/to/json-scada.json
```

本目录不是防火墙上的 MQTT broker，也不会由 core 热部署脚本自动运行。驱动仍使用 JSON-SCADA 的 `protocolDriverInstances` / `protocolConnections` 配置和 MongoDB `realtimeData` 集合。

开发验证：

```sh
npm ci
npm test
```

测试包含真实本地 MQTT broker 与 MQTT 客户端、TCP 套接字拆分/合并及 UTF-8、身份冲突、模型配对、同名通道隔离和采样布局。数据库使用内存替身核对查询及写入条件，尚未验收真实 MongoDB/JSON-SCADA、机床、HA、吞吐或国密握手。

## 连接配置

在既有 `protocolConnections` 文档中配置以下可选字段：

| 字段 | 默认值 | 含义 |
| --- | --- | --- |
| `transport` | `mqtt` | `mqtt` 或 `tcp-json`，不自动探测 |
| `endpointURLs` | MQTT 本地地址 | MQTT 模式使用第一个 broker URL |
| `topicRoot` | 空 | 如 `factory/nclink`，不得含末尾斜杠或通配符 |
| `topicStyle` | `device` | `device` 使用 `Probe/Query/Request/<device>`；`device_endpoint` 附加 `/<scadaHostId>` |
| `sampleLayout` | `rows` | 二维数组；`mtconnect-columns` 显式兼容适配器的 `[{"data":[...]}, ...]` 列布局 |
| `deviceAliases` | 空映射 | 如 `{"01":"adapter-uuid"}`，用于明确约定模型根 ID 与注册身份的映射，不推断别名 |
| `caFile` / `certFile` / `keyFile` | 未配置 | MQTT TLS 的 CA 与客户端证书路径，证书和私钥须成对配置 |
| `useSecurity` | 未启用 | 开启后要求 `mqtts://`；TLS 始终验证服务端证书 |
| `tcpListenHost` / `tcpListenPort` | `127.0.0.1` / `8081` | 仅 TCP JSON 模式使用 |

TLS 文件配置已接入，但不宣称支持国密 GMTLS 双证书、硬件密钥或 TPCM。MQTT 的 Client ID、证书和设备权限仍须在 broker 上绑定并配置 ACL；主题与 JSON 一致性检查不等于设备真实性认证。

MQTT 驱动订阅 `Register/#,Probe/#,Sample/#,Notify/#,Method/#,Event/#,Unregister/#,Query/Request/#,Discovery/Response/#`。在防火墙中单独设置其源地址和订阅规则：选择“订阅”，设备/通道留空，在“额外订阅过滤器”逐项填写这些过滤器，并使用相同的主题根前缀。该规则不授权发布。发布业务另建规则；不要给所有客户端复制驱动的宽订阅权限。

## 采样和模型

先注册，再报告版本，驱动发出模型查询；模型响应必须在 30 秒内匹配该设备的 `@id`，版本须与报告一致。校验并创建标签成功后才启用该模型的通道。重复版本不重复拉取，重复或未配对的模型响应不更新模型。只接受已建模设备/通道的采样，并校验整批行列数。

设备标识支持 `guid`、`cli_uuid`、`dev_uuid`；同时出现时必须相同。主题中的设备也须一致，只有明确配置的 `deviceAliases` 可以归一为同一设备。采样主题通道须等于报文 `id`。不再依赖 `@id` 前缀判断消息类型。

标签以 `protocolSourceCommonAddress=<设备身份>` 和原始 `protocolSourceObjectAddress=<数据项ID>` 联合定位，名称也包含设备身份。升级旧数据库前应备份；旧版空 common-address 标签不会自动迁移或覆盖，需要按真实设备对应关系迁移历史标签和 HMI 引用。

`timestamp/startTime/beginTime` 有效时推算最新采样时刻；没有可靠时间时使用接收时间并标记来源时间未确认。驱动仍只写入每批最新一行。采样批次格式错误会在任何数据写入前拒绝；数据库写入失败不保证跨多个标签的事务回退。

## TCP JSON

这是本修复版的明确封装约定，不宣称是另一种 NC-Link 标准传输：每条消息是一行 JSON，带 `topic` 和对象 `payload`，或在顶层直接放 PDU 字段。示例：

```json
{"topic":"Register/Request","payload":{"@id":"r1","cli_uuid":"dev01"}}
{"topic":"Probe/Version/dev01","payload":{"@id":"v1","guid":"dev01","version":"1.1.0"}}
```

响应也携带 `topic/payload`。首条必须注册，连接随后绑定设备；身份切换、格式错误、超过 1 MiB 缓冲、超出队列上限会断开。TCP 默认只监听 loopback，不自动开放防火墙端口。现有 Suricata NC-Link 规则仍检查 MQTT，不提供此 TCP JSON 内容检查；外部接入须另配网络权限及加密。

模型设置、Query/Set 转发和 Method 下行控制没有新增放行能力；现有拒绝或未实现状态保留。对象级写值白名单应在经过设计与验证的转发执行点实现，不能把此驱动接收端检查算作防火墙已经具备该能力。
