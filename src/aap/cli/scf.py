"""aap scf deploy/status/ip 命令

管理腾讯云 SCF 代理,用于绕开微信公众号 IP 白名单限制。
"""
import typer

app = typer.Typer(help="管理腾讯云 SCF 代理")


@app.command("deploy")
def deploy(
    secret_id: str = typer.Option(..., "--secret-id", help="腾讯云 SecretId"),
    secret_key: str = typer.Option(..., "--secret-key", help="腾讯云 SecretKey"),
    region: str = typer.Option(
        "ap-shanghai", "--region", help="腾讯云地域"
    ),
    function_name: str = typer.Option(
        "aap-wechat-proxy", "--function-name", help="SCF 函数名"
    ),
    scf_secret: str = typer.Option(
        None, "--scf-secret", help="自定义 SCF 访问密钥(默认自动生成)"
    ),
) -> None:
    """部署 SCF 云函数

    部署完成后会输出触发 URL 与 SCF_SECRET,请将它们写入配置:
      aap config set scf.url <触发URL>
      aap config set scf.secret <SCF_SECRET>
      aap config set scf.enabled true
    """
    from aap.scf.deployer import SCFDeployer

    deployer = SCFDeployer(region=region, function_name=function_name)
    try:
        url = deployer.deploy(secret_id, secret_key, scf_secret=scf_secret)
    except RuntimeError as e:
        typer.secho(f"部署失败: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    typer.secho("部署完成", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"触发 URL: {url}")
    typer.echo(f"SCF_SECRET: {deployer.scf_secret}")
    typer.echo("")
    typer.secho("请将以下配置写入 AAP:", fg=typer.colors.CYAN)
    typer.echo(f"  aap config set scf.url {url}")
    typer.echo(f"  aap config set scf.secret {deployer.scf_secret}")
    typer.echo("  aap config set scf.enabled true")


@app.command("status")
def status(
    secret_id: str = typer.Option(..., "--secret-id", help="腾讯云 SecretId"),
    secret_key: str = typer.Option(..., "--secret-key", help="腾讯云 SecretKey"),
    region: str = typer.Option("ap-shanghai", "--region", help="腾讯云地域"),
    function_name: str = typer.Option(
        "aap-wechat-proxy", "--function-name", help="SCF 函数名"
    ),
) -> None:
    """查询 SCF 函数运行状态"""
    from aap.scf.deployer import SCFDeployer

    deployer = SCFDeployer(region=region, function_name=function_name)
    try:
        info = deployer.get_status(secret_id=secret_id, secret_key=secret_key)
    except RuntimeError as e:
        typer.secho(f"查询失败: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if not info.get("exists"):
        typer.secho(f"函数 {function_name} 不存在", fg=typer.colors.YELLOW)
        raise typer.Exit(0)

    typer.secho(f"函数名: {info['function_name']}", fg=typer.colors.CYAN)
    typer.echo(f"运行时: {info.get('runtime', 'N/A')}")
    typer.echo(f"内存:   {info.get('memory', 'N/A')} MB")
    typer.echo(f"超时:   {info.get('timeout', 'N/A')} 秒")
    typer.echo(f"状态:   {info.get('status', 'N/A')}")
    typer.echo(f"修改时间: {info.get('modify_time', 'N/A')}")
    triggers = info.get("triggers", []) or []
    typer.echo(f"触发器: {len(triggers)} 个")
    for t in triggers:
        typer.echo(f"  - {t.get('Type', '?')}: {t.get('TriggerName', '?')}")


@app.command("ip")
def ip(
    scf_url: str = typer.Option(
        None, "--url", help="SCF 触发 URL(覆盖配置文件)"
    ),
    scf_secret: str = typer.Option(
        None, "--secret", help="SCF 访问密钥(覆盖配置文件)"
    ),
) -> None:
    """获取 SCF 函数的出口 IP

    需要已部署 SCF 函数。URL 与 secret 可通过参数或配置文件提供。
    """
    from aap.config.manager import ConfigManager
    from aap.scf.deployer import SCFDeployer

    # 从配置加载默认值
    config = ConfigManager().load()
    url = scf_url or config.scf.url
    secret = scf_secret or config.scf.secret

    if not url:
        typer.secho(
            "未配置 SCF URL,请使用 --url 参数或运行 `aap config set scf.url <URL>`",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    deployer = SCFDeployer(scf_url=url, scf_secret=secret)
    try:
        egress_ip = deployer.get_egress_ip()
    except RuntimeError as e:
        typer.secho(f"获取出口 IP 失败: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if not egress_ip:
        typer.secho("未能获取出口 IP", fg=typer.colors.YELLOW)
        raise typer.Exit(1)

    typer.secho(f"SCF 出口 IP: {egress_ip}", fg=typer.colors.GREEN)
    typer.echo("")
    typer.secho("请将此 IP 添加到微信公众号 IP 白名单:", fg=typer.colors.CYAN)
    typer.echo("  登录微信公众平台 → 设置与开发 → 基本配置 → IP 白名单")
