# Core 开发约定

## 代码托管

- 本项目的主仓库为 `https://gitee.com/xwy6848/core.git`，默认分支为 `master`。
- `origin` 的 fetch/push 均指向该 Gitee 仓库；后续 core 修改、提交和推送在此仓库中进行。
- 更新使用 `git fetch origin` 和 `git pull --ff-only`；保留已有的未提交及未跟踪文件。
- 不向 OPNsense 上游仓库推送本项目修改，不使用强制推送覆盖远端历史。
- 密码、SSH 私钥、API 密钥、设备配置和运行日志不得提交到仓库。

## Ubuntu 与 OPNsense 开发环境

- Ubuntu 工作目录：`/home/sebastian/Industrial-Firewall/core`。
- 测试虚拟机：`192.168.255.136:22`，SSH 用户为 `root`。
- 本机 SSH 别名为 `opnsense-dev`，密钥位于本机 `~/.ssh/id_ed25519_opnsense_dev`。
- 活动 core 源码目录为 `/root/core-review`，插件源码为 `/usr/plugins`；原 `/root/core` 保留旧开发现场。设备为 FreeBSD 14.3、OPNsense 26.1 系列。
- 在 Ubuntu 编辑、提交代码，使用 SSH 在 FreeBSD 上执行系统命令和验证。
- 远端 root 默认使用 csh；多行 POSIX shell 脚本须通过以下方式执行：

  ```sh
  ssh -T -o BatchMode=yes opnsense-dev /bin/sh -s <<'SH'
  set -eu
  cd /root/core
  git status --short
  SH
  ```

## 同步与生效

- 部署前检查本地和远程 Git 状态、源提交、实际挂载及服务状态，备份配置和改动。
- 虚拟机访问 Gitee 可能受其代理设置影响；可在 Ubuntu 获取代码，再以 Git bundle 经 SSH 传到虚拟机，使用 `git merge --ff-only` 更新，保留远端 `origin` 为 Gitee。
- 审核机已停用 unionfs：旧挂载在卸载时发生内核卡死并需要 VMware 重置恢复。禁止在该机重新执行 `make mount`；使用 `Scripts/deploy-review.py` 做普通文件与插件热部署。每次仍以 `mount -p` 核对实际状态。
- unionfs 会将部分运行时文件和插件文件写入源码目录。不要执行 `git clean`，不要把这些文件加入提交，也不要对整个运行目录使用 `rsync --delete`。
- 挂载期间不要安装、升级、删除或打包插件；需要这些操作时先按 README 的流程正常卸载 core。
- 修改 PHP 后使用虚拟机上的 `php -l` 检查；按修改内容重载 configd、清缓存或重启 Web 服务。
- 重新生成 `src/opnsense/version/core` 时必须使用 Makefile 的变量替换规则，使运行版本对应已部署提交；该文件不纳入 Git。
- 必须验证 SSH、Web 登录页和相关服务。直接访问虚拟机时绕过开发机 HTTP 代理，例如 `curl --noproxy '*' http://192.168.255.136/`；协议和端口以设备配置为准。
- 本轮以功能热部署供审核；用户审核通过前不制作 ISO。参见 `docs/FEATURE_REVIEW.md`，性能容量、TPM/TPCM、真实双机 VPN/HA 联调与现有功能测试须分别记录。
