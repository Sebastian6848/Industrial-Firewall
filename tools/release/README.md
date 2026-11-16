# 工业可信防火墙镜像构建

源码位于 [GitHub](https://github.com/Sebastian6848/Industrial-Firewall)，[Gitee](https://gitee.com/xwy6848/core)提供镜像。根目录是 core，`plugins/` 是插件，`tools/` 是镜像工具，`contrib/` 包含 NC-Link 驱动与适配器参考源码。插件原始快照为 `106b7fdd922a4ca6c52be45998006060ba74611e`，工具快照为 `4722ec6a73d286d333ee54f467d318fb96b881fb`；其来源与上游许可证保留在相应目录。NC-Link 适配器和观察代理不打入发布 ISO。产品安装器的定制源码位于 `contrib/installer/`。

## 构建准备

使用独立的 FreeBSD 14.3 amd64/OPNsense 26.1 构建机，安装 Git、Python 3 和带受信仓库密钥的 `pkg`、`opnsense-verify`，预留至少 10 GB 空间。新建输入目录。镜像读取 `upstream-inputs.sha256` 中的每个文件并校验哈希。

- `sets/`：从官方 26.1 amd64 镜像源取得 `base-26.1.11-amd64.txz`、`kernel-26.1.11-amd64.txz` 及同名 `.sig`。
- `vendor/All/`：在已配置 OPNsense 官方签名仓库的构建机上，用 `pkg fetch -d -r OPNsense -o /absolute/inputs/vendor opnsense opnsense-installer os-ntopng os-c-icap os-clamav os-squid` 收集依赖。需要与锁定清单一致的版本。滚动仓库已经更新时应使用已留档的可信包集，或审查新版本后更新锁定清单并重新回归。
- 可以用 `sha256sum -c tools/release/upstream-inputs.sha256` 从 Linux 核对输入，从 FreeBSD 开始构建。构建脚本也单独调用 `opnsense-verify` 验证 base/kernel 签名。

```sh
cd /absolute/core
# /absolute/new-work-dir 必须不存在
sh tools/release/build-iso.sh /absolute/inputs /absolute/output /absolute/new-work-dir
```

脚本用受信系统包创建全新根文件系统，再安装本仓库构建的产品安装器、core、Squid、ClamAV、应用识别、工业白名单、工业安全包。引导与安装由上游 DVD/media 工具驱动；不复制运行设备的凭据、网络配置和数据库。出厂规则来自 `src/etc/config.xml.sample` 与 `examples/app-identification/`。输出 ISO、构建提交号、包清单和原始 ISO 校验值。随机种子和文件打包时间等因素会影响字节级哈希，构建记录用提交和输入清单追踪。

## 发布与维护

先用空白虚拟机完成启动、安装、卸载光驱、系统盘重启和 Web 登录。验证功能和回归范围后，再通过 GitHub Release 发布。镜像以单个 .iso.bz2 文件提供，同时发布压缩镜像与原始 ISO 的 SHA-256。见 [安装与使用说明](../../docs/manual/安装与使用说明.md) 与 [测试报告](../../docs/RELEASE_TEST_REPORT.md)。

实验环境的部署辅助脚本位于 `Scripts/`，使用前需核对主机、目录与备份配置。生产环境应使用经过验证的镜像或软件包升级流程。若要升级底层依赖、系统内核、定制包或规则库，先创建测试构建并按测试报告复验。

## 生成带截图的 PDF 说明书

Markdown 原稿及截图位于 `docs/manual/`。本机安装 Python 包 `playwright`、`markdown-it-py`、Chromium 和简体中文字体（例如 Source Han Sans SC）后执行：

```sh
python3 tools/release/render-manual.py \
  docs/manual/安装与使用说明.md \
  /absolute/output/Industrial-Firewall-Installation-and-User-Manual.pdf
```

使用系统 Chromium 时设置 `CHROMIUM_PATH` 为可执行文件的绝对路径。渲染器验证每张图片均加载成功；PDF 中的跨文档链接指向项目仓库。发布前另行检查页数、中文文本提取和打印版截图。
