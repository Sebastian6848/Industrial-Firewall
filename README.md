# Firewall 核心系统

Firewall 是面向网络边界和工业网络场景的防火墙系统，提供网络接口管理、访问控制、地址转换、入侵检测、VPN、流量监控、服务管理和插件扩展等能力。

本仓库是 Firewall 的核心代码仓库，主要包含 Web 管理界面、配置模型、系统脚本、配置生成模板、后台服务动作和运行时管理逻辑。本文档面向部署人员和开发人员，介绍镜像构建、基础配置、实时开发、调试、打包和发布流程。

> [!WARNING]
> 请先在测试虚拟机中验证源码和插件修改。对接口、防火墙规则、认证、Web 管理服务或软件包的错误操作，可能导致设备失联。

## 1. 环境要求

### 1.1 构建环境

- FreeBSD 14.3-RELEASE amd64
- root 权限
- 至少 8 GB 内存
- 至少 40 GB 可用磁盘空间
- 可访问源码仓库和软件包镜像

完整镜像建议通过独立的 FreeBSD 构建机生成，不要直接在生产防火墙上执行完整镜像构建。

### 1.2 运行环境

虚拟机测试环境建议配置：

| 资源 | 最低配置 | 推荐配置 |
| --- | --- | --- |
| CPU | 2 核 | 4 核及以上 |
| 内存 | 4 GB | 8 GB及以上 |
| 磁盘 | 20 GB | 40 GB及以上 |
| 网卡 | 1 块 | 2 块及以上，分别用于 WAN 和 LAN |

Web 管理界面使用现代浏览器访问，默认应通过 LAN 或专用管理网络连接。

## 2. 仓库结构

核心代码位于 `src/`，常用开发入口如下：

| 路径 | 用途 |
| --- | --- |
| `src/opnsense/mvc/app/controllers` | MVC 页面控制器和 API 控制器 |
| `src/opnsense/mvc/app/models` | 配置模型、菜单、ACL 和数据校验 |
| `src/opnsense/mvc/app/views` | Volt 页面模板和前端逻辑 |
| `src/opnsense/scripts` | Python、PHP 和 Shell 后台脚本 |
| `src/opnsense/service/conf/actions.d` | configd 动作定义 |
| `src/opnsense/service/templates` | 根据系统配置生成服务配置文件的模板 |
| `src/www` | 传统 PHP 页面、公共前端资源和页面入口 |
| `src/etc/rc.d` | 系统服务启动脚本 |
| `src/opnsense/mvc/tests` | MVC 单元测试 |
| `contrib` | 构建所需的辅助组件 |

典型的数据流如下：

```text
Web 页面或 API
    -> MVC Controller
    -> 配置 Model
    -> configd Action
    -> 后台脚本或配置模板
    -> 系统服务
```

修改功能时应先确定变更位于哪一层。仅刷新浏览器不会让新的 configd 动作、配置模板或后台服务代码自动生效。

## 3. 构建安装镜像

### 3.1 获取构建环境

构建仓库建议放在 `/usr` 下：

```sh
pkg install -y git
git clone https://github.com/Sebastian6848/tools /usr/tools
cd /usr/tools
make update
```

`make update` 会根据 `tools` 仓库中的配置获取 core、plugins、src 和 ports 等构建源。执行后应检查各仓库的远程地址、分支和版本是否符合本次发布要求。

### 3.2 推荐构建流程

为了缩短测试镜像的构建时间，可以预取基础系统、内核和软件包，再构建核心代码和镜像：

```sh
cd /usr/tools
make prefetch-base,kernel,packages
make core
make dvd
```

不要在没有必要时直接从头编译基础系统、内核和全部第三方软件包。完整构建会占用较多时间和磁盘空间。

构建完成后，镜像通常位于：

```text
/usr/local/opnsense/build/<版本>/amd64/images/
```

如需从构建虚拟机下载大文件，可以在镜像目录临时启动 HTTP 服务：

```sh
cd /usr/local/opnsense/build/<版本>/amd64/images
python3 -m http.server 8888
```

然后通过 `http://<构建机IP>:8888/` 下载。传输完成后使用 `Ctrl+C` 停止临时服务，不要长期暴露该端口。

### 3.3 常见构建问题

如果构建过程中提示本机 `pkg` 与 ports 版本不兼容，可以在构建机上重新构建并安装包管理器：

```sh
make -C /usr/ports/ports-mgmt/pkg clean all reinstall
```

再次构建前建议确认：

```sh
freebsd-version
uname -m
df -h
git -C /usr/tools status --short
```

不要在存在未确认源码修改时执行会自动更新或替换仓库内容的操作。

## 4. 安装与基础配置

### 4.1 虚拟机安装

1. 新建 64 位虚拟机，分配 CPU、内存和磁盘。
2. 添加安装 ISO，并设置为启动时连接。
3. 测试环境至少准备 WAN、LAN 两块虚拟网卡。
4. 从 ISO 启动，使用镜像提供的安装入口进入安装程序。
5. 选择目标磁盘并完成安装，推荐使用 ZFS 安装方式。
6. 设置管理员密码，安装完成后移除 ISO 并重启。
7. 首次登录后立即确认或修改管理员密码，不要在生产环境使用初始密码。

### 4.2 分配 WAN 和 LAN

可以在控制台菜单中完成接口分配：

1. 选择 **Assign interfaces**。
2. 将连接外部网络的网卡分配为 WAN。
3. 将连接内部或管理网络的网卡分配为 LAN。
4. 没有 VLAN、LAGG 或额外接口需求时跳过对应步骤。
5. 确认接口列表后保存，等待系统重新加载网络配置。

网卡名称取决于虚拟化平台和驱动，可能显示为 `em0`、`igc0`、`vtnet0`、`vmx0` 或其他名称。不要直接照抄示例名称，应根据MAC地址和虚拟机网卡连接关系确认。

### 4.3 配置 LAN 地址

在控制台选择 **Set interface IP address**，为 LAN 设置静态地址，例如：

```text
LAN address: 10.10.10.1
Prefix length: 24
```

根据测试环境需要决定是否在 LAN 启用 DHCP。配置完成后，在 LAN 主机浏览器中访问控制台显示的 HTTPS 地址。

推荐的测试拓扑：

```text
外部测试机 -- WAN [ Firewall ] LAN -- 内部测试机
```

### 4.4 私有地址测试环境

如果 WAN 接入 VMware NAT、Host-Only 或其他私有地址网络，默认的私有网络、保留地址拦截可能影响测试流量。可以在 Web 管理界面的 **接口 > WAN** 中，根据实验拓扑临时调整以下选项：

- 阻止私有网络；
- 阻止保留网络。

> [!CAUTION]
> 该调整仅适合明确使用私有地址作为 WAN 的实验环境。公网部署不要为了排查连通性直接关闭安全限制。

### 4.5 最小连通性测试

防火墙规则应按最小权限创建。实验环境需要测试 WAN 到 LAN 的流量时，可以临时创建限定源地址、目标地址和协议的放行规则，并启用日志。

依次验证：

```sh
# 在两侧主机检查地址和路由
ifconfig
netstat -rn

# 检查目标连通性
ping <目标地址>

# 检查TCP端口
nc -vz <目标地址> <端口>
```

测试结束后删除不再需要的宽泛规则。生产环境不要使用 `any -> any` 规则代替明确的访问策略。

## 5. 核心代码实时开发

当前项目审核虚拟机使用普通文件与插件热部署流程，参见 [功能审核版说明](docs/FEATURE_REVIEW.md)。该机曾发生 unionfs 卸载卡死，后续请使用 `Scripts/deploy-review.py`，不要在该审核机运行下面通用章节的 `make mount`。

### 5.1 启用 SSH

在 Web 管理界面进入 **系统 > 设置 > 管理**，启用 Secure Shell。仅在确有需要时允许管理员远程登录，优先使用密钥认证，并限制 SSH 监听接口和来源地址。

### 5.2 获取源码

在测试防火墙上执行：

```sh
pkg install -y git
cd /root
git clone https://gitee.com/xwy6848/core.git
cd /root/core
```

如果目录中已有源码，先使用 `git status --short` 检查本地修改，不要直接覆盖他人的未提交工作。

### 5.3 热挂载 core

执行以下命令将仓库的 `src/` 以 unionfs 方式挂载到运行系统：

```sh
cd /root/core
make mount
```

当运行make mount没反应时：

```sh
rm -f /root/core/work/.mount_done
```

挂载成功后，对 PHP、Volt、JavaScript、CSS、配置模型和脚本的修改会直接反映到运行目录。部分组件仍可能需要刷新缓存或重启服务：

```sh
service php_fpm onerestart
pluginctl -cq cache_flush
/usr/local/etc/rc.restart_webgui
```

退出开发环境前必须执行：

```sh
cd /root/core
make umount
```

> [!WARNING]
> 重启防火墙、移动或删除 core 目录之前，必须先执行 `make umount`。
>
> core 处于热挂载状态时，不要安装、升级、删除或热部署插件，也不要执行插件目录中的 `make package`、`make upgrade`。unionfs 与 pkg 同时修改运行目录可能造成临时目录、文件重命名或软件包解包异常。需要操作插件时，先执行 `make umount` 并确认挂载已经消失。

检查当前挂载状态：

```sh
mount | grep unionfs
```

### 5.4 挂载异常恢复

首先尝试正常卸载：

```sh
cd /root/core
make umount
mount | grep unionfs
```

只有在确认 unionfs 已经不存在、但 `make mount` 仍认为挂载完成时，才清理残留标记：

```sh
cd /root/core
rm -f work/.mount_done
service configd restart
service php_fpm onerestart
```

不要在 unionfs 仍然挂载时直接删除 `.mount_done`，否则可能重复挂载并进一步破坏目录状态。

## 6. 修改后的生效方式

修改前建议备份系统配置，并保留当前Git差异：

```sh
cp /conf/config.xml /conf/config.xml.before-development
git status --short
git diff
```

不同类型的修改采用不同的加载方式：

| 修改内容 | 通常需要执行的操作 |
| --- | --- |
| Volt、JavaScript、CSS | 强制刷新浏览器，必要时清理浏览器缓存 |
| PHP页面或控制器 | `php -l <文件>`，刷新页面；必要时重启 `php_fpm` |
| MVC模型XML、菜单、ACL | 检查XML和模型结构，重新登录或重启Web相关服务 |
| configd Action | `service configd restart` 后再调用动作 |
| Python后台脚本 | 先直接执行或做语法检查，再重启调用它的服务 |
| 配置模板 | `configctl template reload <模板名称>` |
| rc服务脚本或守护进程 | 重启对应服务并检查状态和日志 |

常用命令：

```sh
# 重载configd动作
service configd restart

# 查看动作是否已经注册
configctl configd lookup <动作名>
configctl configd actions | grep <关键字>

# 重新生成某个服务的配置
configctl template reload OPNsense/<服务模板>

# 重启Web后端
service php_fpm onerestart

# 检查服务
service <服务名> status
service <服务名> restart
```

模板名称必须与 `src/opnsense/service/templates/` 下的目录一致。不要在不清楚影响范围时执行全量模板重载。

## 7. 调试指南

### 7.1 前端和 API

1. 使用浏览器开发者工具检查 Console 和 Network。
2. 确认请求URL、HTTP状态码、请求参数和响应JSON。
3. 对静态资源执行强制刷新，排除浏览器缓存。
4. 直接访问对应API，区分页面渲染问题和后端接口问题。

示例：

```sh
curl -k -u '<用户>:<密码>' \
  'https://<防火墙地址>/api/<模块>/<控制器>/<动作>'
```

不要在共享终端历史、脚本或工单中保存真实管理员密码。调试自动化接口时应使用权限受限的专用账号和API密钥。

### 7.2 PHP 和 MVC

检查PHP语法：

```sh
php -l <文件.php>
```

查看PHP错误：

```sh
tail -f /var/lib/php/tmp/PHP_errors.log
```

如果页面返回空白、500或不完整JSON，应优先检查PHP错误日志、控制器命名空间、路由、ACL和模型校验结果。

### 7.3 configd 和后台脚本

先直接运行后台脚本，确认脚本本身能够正常工作，再通过configd调用：

```sh
python3 -m py_compile <脚本.py>
python3 <脚本.py> <参数>

service configd restart
configctl configd lookup <动作名>
configctl <模块> <动作> <参数>
```

查看configd日志：

```sh
opnsense-log -f configd
```

如果直接运行脚本成功、但 `configctl` 返回 `Action not allowed or missing`，通常应检查：

- Action文件是否位于 `src/opnsense/service/conf/actions.d/`；
- `[动作名]`、`command`、`parameters` 和 `type` 是否正确；
- 是否已经重启configd；
- Web用户是否具备对应API或页面ACL。

### 7.4 服务、进程和端口

```sh
service <服务名> status
service <服务名> restart
pgrep -af <进程关键字>
sockstat -4 -6 -l
```

服务启动失败时，同时检查：

- 生成的配置文件是否存在且内容正确；
- 配置文件属主和权限；
- 监听地址或端口是否冲突；
- rc变量和启动参数；
- 服务自身日志和configd日志。

### 7.5 软件包调试

```sh
pkg info <软件包名>
pkg check -d
pkg check -s
pkg which <文件路径>
```

安装前可以先查看事务，不自动确认：

```sh
pkg install <软件包名>
```

确认待安装、删除和升级的软件包符合预期后再继续。不要为了安装单个插件而忽略ABI、依赖冲突或核心软件包替换提示。

### 7.6 常见故障排查

| 现象 | 优先检查 | 处理方式 |
| --- | --- | --- |
| 页面修改后没有变化 | 浏览器缓存、文件是否位于热挂载目录 | 强制刷新，确认unionfs挂载和实际加载文件 |
| 页面返回500或空白 | PHP错误日志、语法、控制器路由 | 执行`php -l`并查看`PHP_errors.log` |
| `Action not allowed or missing` | Action名称、文件位置、configd缓存、ACL | 修正Action，重启configd，使用`configd lookup`验证 |
| 配置保存但服务配置未变化 | 模板名称、模型字段、模板渲染错误 | 单独执行`template reload`并检查生成文件和日志 |
| 服务无法启动 | 配置语法、端口冲突、权限、rc参数 | 直接执行服务检查命令，查看服务及configd日志 |
| `make mount`没有生效 | unionfs状态、`.mount_done`标记 | 先正常卸载；确认无挂载后再清理残留标记 |
| 插件安装出现临时目录或rename错误 | core是否仍处于unionfs热挂载 | 先卸载core并确认挂载消失，再清理失败事务并重装 |
| 插件无法安装或要求替换大量系统包 | ABI、仓库版本、依赖和冲突 | 取消事务，使用匹配当前系统版本的插件包重新构建 |

## 8. 检查、打包与发布

### 8.1 代码检查

提交或打包前，在core仓库执行：

```sh
cd /root/core
make lint
make style
make test
```

- `make lint`：检查plist、Shell、XML、模型、ACL、PHP等内容。
- `make style`：检查Python和MVC PHP代码风格。
- `make test`：运行仓库测试。

测试命令应在与目标版本一致的防火墙开发环境中运行。检查结果通过不代表功能已经完成，仍需进行页面、API和服务级回归测试。

### 8.2 core 打包与升级

打包前必须退出热挂载：

```sh
cd /root/core
make umount
mount | grep unionfs
make package
```

`make package` 生成当前core源码的软件包；`make upgrade` 会生成软件包并替换测试系统中已安装的core包。`make upgrade` 具有更大影响，只能在测试环境使用：

```sh
cd /root/core
make upgrade
```

升级后检查Web界面、configd、网络接口、防火墙规则和关键服务，不要只验证登录页。

### 8.3 插件开发和安装

插件源码由独立仓库维护：

```sh
git clone https://gitee.com/xwy6848/plugins.git /usr/plugins
cd /usr/plugins/<分类>/<插件>
```

开发环境可以在插件目录构建和部署：

```sh
make package
# 或仅在测试防火墙上执行
make upgrade
```

离线安装时，将生成的 `.pkg` 或 `.txz` 文件及其依赖复制到目标设备，再使用本地包安装：

```sh
pkg add /root/<插件软件包>
```

> [!IMPORTANT]
> 操作插件前必须确认core没有处于热挂载状态。插件及依赖必须与目标防火墙的FreeBSD ABI和系统版本兼容。

当前系统默认冻结常规系统更新，插件发现和安装通道独立保留。插件安装仍可能拉取、安装或更新其运行依赖，因此必须审查完整的pkg事务。详细策略参见 [插件仓库与更新策略](PRIVATE_PLUGINS.md)。

## 9. 安全建议

- Web管理和SSH仅监听可信接口，并通过防火墙规则限制来源地址。
- 使用强密码和独立管理员账号，优先采用密钥或证书认证。
- 不在源码、日志、截图和命令历史中保存密码、私钥或API密钥。
- 修改接口、认证和防火墙规则前备份 `/conf/config.xml`。
- 安装插件前审查来源、签名、ABI、依赖、安装脚本和pkg事务。
- 生产升级前在同版本测试环境完成安装、重启、断网恢复和回滚验证。
- 临时调试规则、HTTP服务和远程管理入口在测试结束后立即关闭。

## 10. 许可证

本仓库的许可条件见 [LICENSE](LICENSE)。分发源码、二进制软件包或安装镜像时，应遵守许可证要求并保留其中要求的版权、许可条件和免责声明。
