# 阿里云 Ubuntu 24.04 部署：服务器内部启动

适用于当前 `admin` 用户、Python 3.12.3 和已创建的 `/home/admin/chronomem/.venv`。程序是文本 BM25 检索基线，尚未通过官方 Smoke 或 Full。

## 上传

通过 Workbench 左侧文件管理，将 `chronomem-server.zip` 上传到 `/home/admin`。该目录支持当前 admin 一键连接上传。

在服务器终端执行：

```bash
unzip -o /home/admin/chronomem-server.zip -d /home/admin/chronomem
/home/admin/chronomem/.venv/bin/python /home/admin/chronomem/install_server.py
```

最初的 0.2 源码包以 Git 版本 a2e3030 为基础；当前 0.3 升级包包含 BM25 程序、索引模块与升级脚本。正式申报时使用完成升级及公开材料后的实际固定 Commit。压缩包不包含电脑上的 `.env`、数据库、虚拟环境或 Git 凭证。Render 配置文件在本次 Ubuntu 部署中不使用。

## 安装行为

脚本使用已安装的虚拟环境检查 Python 依赖，生成独立的服务器 API 密钥，然后注册并启动 systemd 服务 `chronomem`。密钥保存在项目 `.env` 中，权限为 600；再次运行脚本会保留已有非空密钥。

程序使用 admin 身份运行，进程禁止获得新权限，并以只读方式访问主目录和系统文件；仅项目的 `data` 目录允许持久写入。脚本不会更改防火墙或自动配置公网 HTTP/HTTPS。

服务监听 `127.0.0.1:8000`。程序随终端关闭继续运行，服务器重启后由 systemd 自动启动。安装脚本最后应显示健康检查 JSON，以及：

```text
ChronoMem service is running. Automatic startup is enabled.
```

数据目录：`/home/admin/chronomem/data/chronomem_contract.db`。

## 排查与管理

```bash
sudo systemctl status chronomem --no-pager
sudo journalctl -u chronomem -n 40 --no-pager
curl -fsS http://127.0.0.1:8000/health
```

需要主动停止时：

```bash
sudo systemctl stop chronomem
```

需要启动时：

```bash
sudo systemctl start chronomem
```

后续仍需配置公网 HTTPS、验证 Add/Search 与鉴权、测试数据重启后保留、申请评测并通过官方 Smoke。正式 Full 前还需改进检索并验证容量。

## 参考

- https://help.aliyun.com/zh/simple-application-server/user-guide/use-workbench-to-transfer-files-to-a-linux-server
- https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
