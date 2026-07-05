"""腾讯云 SCF 部署器

负责部署、查询状态与获取出口 IP,用于绕开微信公众号 IP 白名单限制。

部署流程:
1. 读取 function_src/main.py 作为函数代码
2. 用 tencentcloud-sdk 创建或更新 SCF 函数
3. 配置环境变量 SCF_SECRET(访问密钥)
4. 配置 API 网关 HTTP 触发器
5. 返回触发 URL

依赖:
    tencentcloud-sdk-python(optional, 通过 `pip install aap[scf]` 安装)
"""
from __future__ import annotations

import json
import secrets
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional

# SCF 函数源码目录(本文件同级 function_src)
FUNCTION_SRC_DIR = Path(__file__).parent / "function_src"

# 默认函数配置
DEFAULT_FUNCTION_NAME = "aap-wechat-proxy"
DEFAULT_RUNTIME = "Python3.10"
DEFAULT_MEMORY = 128  # MB
DEFAULT_TIMEOUT = 60  # 秒
DEFAULT_DESCRIPTION = "AAP 微信公众号 API 代理(绕开 IP 白名单)"


class SCFDeployer:
    """腾讯云云函数(SCF)部署器

    负责部署、查询状态与获取出口 IP,
    用于绕开微信公众号 IP 白名单限制。

    依赖 tencentcloud-sdk-python,通过 `pip install aap[scf]` 安装。
    """

    def __init__(
        self,
        region: str = "ap-shanghai",
        function_name: str = DEFAULT_FUNCTION_NAME,
        scf_url: Optional[str] = None,
        scf_secret: Optional[str] = None,
    ) -> None:
        """初始化部署器

        Args:
            region: 腾讯云地域(默认 ap-shanghai)
            function_name: SCF 函数名
            scf_url: 已部署的 SCF 触发 URL(用于 get_egress_ip)
            scf_secret: SCF 访问密钥(用于 get_egress_ip 请求验证)
        """
        self.region = region
        self.function_name = function_name
        self.scf_url = scf_url
        self.scf_secret = scf_secret
        self._client: Any = None

    def deploy(
        self,
        secret_id: str,
        secret_key: str,
        scf_secret: Optional[str] = None,
    ) -> str:
        """部署 SCF 云函数

        流程:
        1. 打包 function_src/main.py 为 ZIP
        2. 创建或更新 SCF 函数
        3. 配置环境变量 SCF_SECRET
        4. 创建 API 网关触发器(若不存在)
        5. 返回触发 URL

        Args:
            secret_id: 腾讯云 SecretId
            secret_key: 腾讯云 SecretKey
            scf_secret: 自定义 SCF 访问密钥(为 None 时自动生成 32 位随机字符串)

        Returns:
            SCF 触发 URL

        Raises:
            RuntimeError: SDK 未安装或部署失败
        """
        client = self._get_client(secret_id, secret_key)

        # 生成或使用传入的 SCF_SECRET
        if scf_secret is None:
            scf_secret = secrets.token_urlsafe(24)
        self.scf_secret = scf_secret

        # 打包函数代码
        zip_path = self._pack_function_code()

        try:
            zip_bytes = zip_path.read_bytes()

            # 检查函数是否已存在
            existing = self._try_get_function(client)

            if existing is None:
                # 创建新函数
                self._create_function(client, zip_bytes, scf_secret)
            else:
                # 更新函数代码与环境变量
                self._update_function(client, zip_bytes, scf_secret)

            # 创建或获取 HTTP 触发器
            trigger_url = self._ensure_trigger(client)

            return trigger_url
        finally:
            # 清理临时 ZIP
            try:
                zip_path.unlink(missing_ok=True)
            except OSError:
                pass

    def get_status(self, secret_id: str = "", secret_key: str = "") -> dict:
        """查询 SCF 函数运行状态

        Args:
            secret_id: 腾讯云 SecretId(若 client 未初始化则必须提供)
            secret_key: 腾讯云 SecretKey(若 client 未初始化则必须提供)

        Returns:
            状态信息字典,包含函数名/运行时/内存/超时/状态/触发器列表

        Raises:
            RuntimeError: SDK 未安装或查询失败
        """
        client = self._get_client(secret_id, secret_key)
        func = self._try_get_function(client)
        if func is None:
            return {"exists": False, "function_name": self.function_name}

        triggers = self._list_triggers(client)
        return {
            "exists": True,
            "function_name": self.function_name,
            "runtime": func.get("Runtime"),
            "memory": func.get("MemorySize"),
            "timeout": func.get("Timeout"),
            "status": func.get("Status"),
            "modify_time": func.get("ModifyTime"),
            "triggers": triggers,
        }

    def get_egress_ip(self) -> str:
        """获取 SCF 函数的出口 IP

        通过调用已部署 SCF 函数的专用端点获取出口 IP。

        Returns:
            出口 IP 地址字符串(获取失败返回空字符串)

        Raises:
            RuntimeError: 未配置 scf_url 或请求失败
        """
        if not self.scf_url:
            raise RuntimeError("未配置 scf_url,无法获取出口 IP")

        import httpx

        payload = {
            "secret": self.scf_secret or "",
            "method": "GET",
            "path": "/egress-ip",
            "params": {},
            "body_type": "json",
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(self.scf_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise RuntimeError(f"请求 SCF 失败: {e}") from e

        # SCF main_handler 返回 {statusCode, body: {status_code, body, error}}
        # 需要提取内层 body 中的 ip
        outer = data if isinstance(data, dict) else {}
        if isinstance(outer, str):
            try:
                outer = json.loads(outer)
            except json.JSONDecodeError:
                outer = {}

        middle = outer.get("body", {}) if isinstance(outer, dict) else {}
        if isinstance(middle, str):
            try:
                middle = json.loads(middle)
            except json.JSONDecodeError:
                middle = {}

        if isinstance(middle, dict) and middle.get("error"):
            raise RuntimeError(f"SCF 返回错误: {middle['error']}")

        inner = middle.get("body", {}) if isinstance(middle, dict) else {}
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except json.JSONDecodeError:
                inner = {}

        ip = inner.get("ip", "") if isinstance(inner, dict) else ""
        return str(ip) if ip else ""

    # ===== 内部工具 =====

    def _get_client(self, secret_id: str, secret_key: str) -> Any:
        """初始化腾讯云 SCF 客户端(惰性)"""
        if self._client is not None:
            return self._client

        if not secret_id or not secret_key:
            raise RuntimeError("必须提供 secret_id 和 secret_key")

        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import (
                ClientProfile,
            )
            from tencentcloud.common.profile.http_profile import (
                HttpProfile,
            )
            from tencentcloud.scf.v20180416 import scf_client, models
        except ImportError as e:
            raise RuntimeError(
                "tencentcloud-sdk-python 未安装,请运行: "
                "pip install 'aap[scf]' 或 pip install tencentcloud-sdk-python"
            ) from e

        cred = credential.Credential(secret_id, secret_key)
        http_profile = HttpProfile(endpoint=f"scf.{self.region}.tencentcloudapi.com")
        client_profile = ClientProfile(httpProfile=http_profile)
        self._client = scf_client.ScfClient(cred, self.region, client_profile)
        return self._client

    def _pack_function_code(self) -> Path:
        """将 function_src/main.py 打包为 ZIP,返回临时文件路径"""
        if not FUNCTION_SRC_DIR.exists():
            raise RuntimeError(f"SCF 函数源码目录不存在: {FUNCTION_SRC_DIR}")

        main_path = FUNCTION_SRC_DIR / "main.py"
        if not main_path.exists():
            raise RuntimeError(f"SCF 函数入口文件不存在: {main_path}")

        # 创建临时 ZIP 文件
        tmp_dir = Path(tempfile.mkdtemp(prefix="aap_scf_"))
        zip_path = tmp_dir / "function.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(main_path, arcname="main.py")
            # 包含其他可能的依赖文件(如 requirements.txt)
            req_path = FUNCTION_SRC_DIR / "requirements.txt"
            if req_path.exists():
                zf.write(req_path, arcname="requirements.txt")

        return zip_path

    def _try_get_function(self, client: Any) -> Optional[dict]:
        """查询函数是否已存在,返回函数信息或 None"""
        from tencentcloud.scf.v20180416 import models

        req = models.GetFunctionRequest()
        req.FunctionName = self.function_name
        req.Namespace = "default"

        try:
            resp = client.GetFunction(req)
            return resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)
        except Exception as e:
            # 函数不存在时腾讯云返回 ResourceNotFound
            if "ResourceNotFound" in str(type(e).__name__) or "NotFound" in str(e):
                return None
            raise RuntimeError(f"查询函数失败: {e}") from e

    def _create_function(
        self, client: Any, zip_bytes: bytes, scf_secret: str
    ) -> None:
        """创建新 SCF 函数"""
        from tencentcloud.scf.v20180416 import models

        req = models.CreateFunctionRequest()
        req.FunctionName = self.function_name
        req.Namespace = "default"
        req.Runtime = DEFAULT_RUNTIME
        req.MemorySize = DEFAULT_MEMORY
        req.Timeout = DEFAULT_TIMEOUT
        req.Description = DEFAULT_DESCRIPTION
        req.Handler = "main.main_handler"
        req.Code = models.Code()
        req.Code.ZipFile = zip_bytes
        req.Environment = models.Environment()
        req.Environment.Variables = [
            models.Variable(Key="SCF_SECRET", Value=scf_secret),
        ]

        try:
            client.CreateFunction(req)
        except Exception as e:
            raise RuntimeError(f"创建函数失败: {e}") from e

    def _update_function(
        self, client: Any, zip_bytes: bytes, scf_secret: str
    ) -> None:
        """更新已有 SCF 函数的代码与环境变量"""
        from tencentcloud.scf.v20180416 import models

        # 1. 更新代码
        code_req = models.UpdateFunctionCodeRequest()
        code_req.FunctionName = self.function_name
        code_req.Namespace = "default"
        code_req.Handler = "main.main_handler"
        code_req.ZipFile = zip_bytes

        try:
            client.UpdateFunctionCode(code_req)
        except Exception as e:
            raise RuntimeError(f"更新函数代码失败: {e}") from e

        # 2. 更新环境变量
        conf_req = models.UpdateFunctionConfigurationRequest()
        conf_req.FunctionName = self.function_name
        conf_req.Namespace = "default"
        conf_req.Environment = models.Environment()
        conf_req.Environment.Variables = [
            models.Variable(Key="SCF_SECRET", Value=scf_secret),
        ]

        try:
            client.UpdateFunctionConfiguration(conf_req)
        except Exception as e:
            raise RuntimeError(f"更新函数配置失败: {e}") from e

    def _ensure_trigger(self, client: Any) -> str:
        """确保 HTTP 触发器存在,返回触发 URL"""
        triggers = self._list_triggers(client)

        for t in triggers:
            if t.get("Type") == "apigw":
                # 已有 API 网关触发器,提取 URL
                info = t.get("TriggerInfo", "")
                url = self._extract_trigger_url(info)
                if url:
                    return url

        # 创建新触发器
        return self._create_trigger(client)

    def _list_triggers(self, client: Any) -> list[dict]:
        """列出函数的所有触发器"""
        from tencentcloud.scf.v20180416 import models

        req = models.ListTriggersRequest()
        req.FunctionName = self.function_name
        req.Namespace = "default"
        req.Limit = 20

        try:
            resp = client.ListTriggers(req)
            data = resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)
            return data.get("Triggers", []) or []
        except Exception:
            return []

    def _create_trigger(self, client: Any) -> str:
        """创建 API 网关触发器"""
        from tencentcloud.scf.v20180416 import models

        req = models.CreateTriggerRequest()
        req.FunctionName = self.function_name
        req.Namespace = "default"
        req.TriggerName = "aap_http"
        req.Type = "apigw"
        req.TriggerDesc = json.dumps({
            "api": {
                "authRequired": "FALSE",
                "requestMethod": "POST",
                "isIntegrated": "TRUE",
                "isBase64Encoded": "FALSE",
                "path": "/aap-proxy",
            },
            "service": {
                "serviceName": "AAP_PROXY",
            },
            "release": {"environmentName": "release"},
        })

        try:
            resp = client.CreateTrigger(req)
            data = resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)
            info = data.get("TriggerInfo", "")
            url = self._extract_trigger_url(info)
            if not url:
                raise RuntimeError("触发器已创建但未提取到 URL,请到腾讯云控制台查看")
            return url
        except Exception as e:
            raise RuntimeError(f"创建触发器失败: {e}") from e

    def _extract_trigger_url(self, trigger_info: Any) -> str:
        """从触发器信息中提取 URL

        Args:
            trigger_info: 触发器信息(字符串或字典)

        Returns:
            触发 URL,提取失败返回空字符串
        """
        if not trigger_info:
            return ""

        # trigger_info 通常是 JSON 字符串
        if isinstance(trigger_info, str):
            try:
                info = json.loads(trigger_info)
            except json.JSONDecodeError:
                return ""
        elif isinstance(trigger_info, dict):
            info = trigger_info
        else:
            return ""

        # 尝试多个可能的 URL 字段
        for key in ("url", "URL", "Url", "service_url"):
            if info.get(key):
                return str(info[key])

        # API 网关标准字段
        service = info.get("service") or {}
        env = service.get("release") or {}
        if env.get("domain"):
            return str(env["domain"])

        return ""
