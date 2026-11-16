# 工业协议白名单

入口：**防火墙 → 工业协议白名单**。当前提供 11 类协议/协议族的策略。协议说明与实现边界集中保留在本说明书中；规则编辑器提供相应操作码。

| 协议 | 默认端口 | 本期控制内容 |
| --- | --- | --- |
| Modbus TCP | TCP/502 | 原生事务解析：功能码、Unit ID |
| DNP3 | TCP/20000 | 原生功能码；默认拒绝不支持对象组允许条件 |
| S7comm | TCP/102 | BETA：基本 TPKT/COTP S7 Job 读/写 |
| MQTT | TCP/1883 | CONNECT 身份、PUBLISH/SUBSCRIBE/UNSUBSCRIBE、主题、QoS |
| NC-Link over MQTT | TCP/1883 | 主题业务操作、方向、设备、客户端/通道及发布/订阅 |
| EtherNet/IP / CIP | TCP/44818 | 原生封装命令与基础 CIP 服务码 |
| IEC 60870-5-104 | TCP/2404 | BETA：I 帧 ASDU 类型 |
| OMRON FINS/TCP | TCP/9600 | BETA：请求命令码 |
| MELSEC MC / SLMP | TCP/5000（依 PLC 配置） | BETA：3E 二进制 TCP 请求命令 |
| BACnet/IP | UDP/47808 | BETA：局域 IPv4 BVLC 的未分段 APDU 服务 |
| OPC UA TCP | TCP/4840 | BETA：HEL/OPN/MSG/CLO 等传输消息类型 |

## 配置方式

选择源、目标和目标端口，选择协议及允许/阻断动作。新协议可用“读取预设”“写入预设”和“填入默认端口”，也可填写操作码；留空操作码时使用原有读/写选项映射。新协议不自动扩大已有策略的范围。目的端口留空继续保持旧版的任意端口含义，建议显式填写。

- IEC-104 操作码为十进制 ASDU 类型，例如 `100` 总召唤、`45` 单命令。
- FINS 与 MELSEC 为四位十六进制命令，例如 FINS `0101` 读取、`0102` 写入；MELSEC `0401` 读取、`1401` 写入。
- EtherNet/IP 封装命令为十进制，例如 `101` RegisterSession、`111` SendRRData；CIP 服务另填十进制，例如 `14` GetAttributeSingle、`16` SetAttributeSingle。读取/写入按钮填充封装命令，CIP 预设取决于“Operation”读写选项或显式服务码。
- BACnet 用 `c` 表示 confirmed、`u` 表示 unconfirmed，例如 `c12` ReadProperty、`c15` WriteProperty、`u8` Who-Is。
- OPC UA 直接填写 `HEL,OPN,MSG,CLO`。这些是传输消息类型，**允许 MSG 不代表只允许读操作**，不会解析加密服务体或节点权限。

默认拒绝按每个配置的源/目标/目标端口范围分别生成未授权操作的拒绝规则；只记录规则不构成允许权限。显式阻断优先，允许规则使用事务审计而不是 Suricata `pass`，不会让一次允许操作绕过后续检查。建议同一协议使用相同的范围汇总允许操作；不同、相互重叠的范围会各自执行默认拒绝，较宽范围的拒绝可能覆盖较窄范围的允许。

当前审核机在线仍运行 IDS/PCAP。实际丢包要求适当接口和拓扑下的 IPS；离线 `--simulate-ips` 验证不能替代在线验收。“日志”中“策略动作”描述策略意图，“实际处置”以引擎事件中的 blocked/allowed 为准，IDS 告警会显示“仅观测 / 告警”。

## NC-Link

现有策略兼容保留，新增了带第二个标识的完整主题：例如 `Query/Request/<device>/<ex_cid>`、`Sample/<device>/<channel>`。同时支持旧的设备级主题。可选“客户端 / 采样通道”字段需先指定设备 UUID；留空时兼容有、无后缀两种形式。

本期覆盖注册、版本探测、模型查询/设置、数据查询/设置、采样上报与采样注册/注销，以及方法调用、方法控制、进度、结果、事件注册/注销、事件上报、状态通知与终端发现等 18 类操作。按 MQTT 主题中的请求/响应语义筛选，采样和事件上报独立于请求/响应方向。注册请求是全局主题，不包含设备标识。空的旧版操作列表仍只映射原有九类，不自动授权新增方法或事件。

选择 MQTT 报文为 PUBLISH、SUBSCRIBE 或两者；订阅过滤器中的 `+/#` 不作为设备业务主题授权，固定设备和端点时不会被通配订阅绕过。控制点是客户端发往 broker 的消息，broker 转发给客户端的响应不属于该方向的过滤范围。应为每个发布者/订阅者分别配置源地址。

默认拒绝会阻断该 NC-Link 范围内所有未授权的、被选择的 PUBLISH/SUBSCRIBE，包括未知主题。不要把无关 MQTT 客户端纳入相同范围；同一范围叠加 MQTT 默认拒绝策略会同时生效。此功能不自动配置 broker ACL，不进行 MQTT TLS 解密，也不验证完整 NC-Link JSON 模型、方法参数、对象值或设备真实性。可见的安全审计字段包含业务操作、主题、设备、客户端/通道及方向，实际字段取决于引擎日志元数据。

### 适配器与驱动兼容配置

规则可填写“主题根前缀”，例如 `factory/nclink`，匹配 `factory/nclink/Sample/<device>/<channel>`；留空维持裸主题。新增状态通知 `Notify/State/<terminal>` 和终端发现 `Discovery/Request/<terminal>` / `Discovery/Response/<terminal>`。新增操作需明确选择，不自动扩大旧规则授权。

“额外订阅过滤器”只授权 SUBSCRIBE，逗号分隔，自动加上同一根前缀。例如为驱动的专用源地址建立订阅规则，填写 `Probe/#,Sample/#`；设备与通道条件留空。它不授权 PUBLISH；通配过滤器与设备条件混用会被拒绝。Broker 仍需身份认证及 ACL，不能把驱动的宽订阅权限授予普通适配器。MQTT 共享订阅不在当前支持范围内。

审计补充 `@id`、报文设备、通道、数据项和采样时间，不导出写入值或凭据。报文设备与主题设备分开显示，审计提取不表示已执行 JSON 身份或写值校验。日志列选择器可显示新增字段，实际可见性取决于 EVE 是否包含消息体。

修复版 JSON-SCADA 驱动在 core 仓库的 `contrib/nclink-driver/`，支持明确的主题后缀与采样布局配置；需要在 JSON-SCADA 主机部署。不要把驱动的 TCP JSON 接收路径计为此插件的 TCP JSON 深度检测能力。

## 实现边界

报文特征协议在重组 TCP 流或 UDP 负载中匹配特征头与操作字段；已覆盖所测拆分、合并和连接复用场景，但不是完整帧解析器，不能保证覆盖任意重组边界、变体、畸形帧或内嵌相似特征的数据。生产白名单应结合真实设备抓包验证，配合网络层只允许必要通信对。

- EtherNet/IP 不涵盖隐式 I/O 的 UDP 流量及完整符号路径、嵌套/多服务授权。基础路径之外的请求不可视作已经完整限制。
- IEC-104 不约束 S/U 控制帧业务权限；不覆盖串行 IEC-101。
- FINS 不覆盖 UDP；MELSEC 不覆盖 ASCII、1E/4E 或 UDP。
- BACnet 只支持 Original-Unicast/Broadcast、无路由 NPDU、未分段 APDU。默认拒绝时阻断纳管范围内不支持的 BVLC 布局，包含路由和分段变体。
- S7comm Plus、PROFINET/EtherCAT 等二层协议、串行现场总线及加密业务体不在本期支持范围。

## 验证

```sh
python3 -m unittest discover -s /usr/plugins/security/icsguard/src/opnsense/scripts/indproto/tests
python3 /usr/plugins/security/icsguard/src/opnsense/scripts/indproto/tests/replay_transactions.py /root/review-original-protocols
python3 /usr/plugins/security/icsguard/src/opnsense/scripts/indproto/tests/replay_extended.py /root/review-expanded-protocols
```

输出目录须为空或使用新目录，以避免混入之前的 EVE 结果。回放不修改在线接口或规则。除单元测试外，还验证了真实 API 存储中文描述、六个新协议和完整 NC-Link 字段、全部策略在设备上的生成/引擎校验/应用，以及浏览器中的操作预设和日志筛选。

## 协议参考

- [Suricata 8 ENIP/CIP 关键字](https://docs.suricata.io/en/suricata-8.0.1/rules/enip-keyword.html)
- [Wireshark IEC-104 解析器](https://github.com/wireshark/wireshark/blob/master/epan/dissectors/packet-iec104.c)
- [OMRON FINS/TCP 官方示例](https://www.fa.omron.com.cn/upload/faqfiles/201806200316173668.pdf)
- [Mitsubishi FX5 SLMP 官方手册](https://www.mitsubishielectric.com/dl/fa/document/manual/plcf/jy997d56001/jy997d56001k.pdf)
- [BACnet Stack 服务定义](https://github.com/bacnet-stack/bacnet-stack/blob/master/src/bacnet/bacenum.h)
- [OPC Foundation 传输消息结构](https://reference.opcfoundation.org/specs/OPC-10000-6/7.1.2)
- [NC-Link 适配接口公开资料](https://patents.google.com/patent/CN113609047A/en)

公开资料用于核对协议字段，不宣称符合全部标准版本或取得认证。实际设备的 NC-Link 主题及业务模型可在这些边界内继续适配。
