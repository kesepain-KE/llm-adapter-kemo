"""
Provider 注册中心。

扫描 ``provider/<name>/model.json``，按 capability 加载模块，
结合 ``config/config.json`` 判断 provider 是否启用。

用法::

    reg = Registry(project_root="/path/to/project")
    reg.load_all()
    chat = reg.get_chat("deepseek")
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 已知 capability → 模块后缀 映射
# ---------------------------------------------------------------------------
CAPABILITY_MODULE: dict[str, str] = {
    "chat": "chat",
    "token_count": "token_count",
    "audio": "audio",
    "image": "image",
    "video": "video",
    "embedding": "embedding",
    "rerank": "rerank",
}


# ---------------------------------------------------------------------------
# 注册中心
# ---------------------------------------------------------------------------

class Registry:
    """加载并管理所有 provider 模块。"""

    def __init__(self, project_root: str | Path = "."):
        self._root = Path(project_root)
        self._provider_dir = self._root / "provider"

        # provider_name → model.json 内容
        self._provider_configs: dict[str, dict[str, Any]] = {}

        # (provider, module_key) → 模块实例
        # e.g. ("deepseek", "chat") → DeepSeekChat instance
        self._modules: dict[tuple[str, str], Any] = {}

        # provider → {capability: bool} 可用能力
        self._capabilities: dict[str, dict[str, bool]] = {}

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def load_all(self) -> None:
        """加载所有 provider 的已启用模块。"""
        if not self._provider_dir.is_dir():
            logger.warning("provider directory not found: %s", self._provider_dir)
            return

        global_config = self._load_config_json()

        for entry in sorted(self._provider_dir.iterdir()):
            if not entry.is_dir():
                continue

            provider_name = entry.name
            model_json = entry / "model.json"
            if not model_json.is_file():
                logger.debug("skip %s: no model.json", provider_name)
                continue

            try:
                provider_cfg = json.loads(model_json.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("failed to read %s: %s", model_json, exc)
                continue

            # 全局开关 (config/config.json)
            g_enabled = (
                global_config.get("providers", {})
                .get(provider_name, {})
                .get("enabled", True)
            )
            # provider 自身开关
            p_enabled = provider_cfg.get("enabled", True)

            if not g_enabled or not p_enabled:
                logger.info("provider '%s' is disabled", provider_name)
                self._provider_configs[provider_name] = provider_cfg
                self._capabilities[provider_name] = {}
                continue

            self._provider_configs[provider_name] = provider_cfg
            self._load_modules(provider_name, provider_cfg)

    def _load_modules(
        self, provider_name: str, config: dict[str, Any]
    ) -> None:
        """按 model.json 的 modules 声明加载各个模块。"""
        modules_decl = config.get("modules", {})
        caps: dict[str, bool] = {}

        # 先加载 package 本身（获取工厂函数）
        pkg_name = f"provider.{provider_name}"
        try:
            pkg = importlib.import_module(pkg_name)
        except ImportError:
            logger.debug("package '%s' not found", pkg_name)
            pkg = None

        for capability_key, module_suffix in CAPABILITY_MODULE.items():
            if capability_key not in modules_decl:
                continue

            instance = None

            # 1) 尝试从 package __init__ 里找工厂函数
            if pkg is not None:
                factory_name = f"create_{module_suffix}"
                factory = getattr(pkg, factory_name, None)
                if factory is not None:
                    try:
                        instance = factory(config)
                    except Exception as exc:
                        logger.warning(
                            "factory '%s.%s' failed: %s",
                            pkg_name, factory_name, exc,
                        )

            # 2) 回退：直接加载子模块，再找工厂 / 类
            if instance is None:
                mod_pkg = f"provider.{provider_name}.{module_suffix}"
                try:
                    mod = importlib.import_module(mod_pkg)
                except ImportError:
                    logger.debug(
                        "module '%s' not found for provider '%s'",
                        module_suffix,
                        provider_name,
                    )
                    caps[capability_key] = False
                    continue

                factory_name = f"create_{module_suffix}"
                factory = getattr(mod, factory_name, None)
                if factory is not None:
                    try:
                        instance = factory(config)
                    except Exception as exc:
                        logger.warning(
                            "factory '%s.%s' failed: %s",
                            mod_pkg, factory_name, exc,
                        )

                # 3) 回退：直接找类
                if instance is None:
                    cls = _find_class_in_module(mod, module_suffix, provider_name)
                    if cls is not None:
                        try:
                            instance = cls(config=config)
                        except Exception as exc:
                            logger.warning(
                                "class '%s' init failed: %s",
                                cls.__name__, exc,
                            )

            if instance is not None:
                self._modules[(provider_name, capability_key)] = instance
                caps[capability_key] = True
                logger.info(
                    "loaded %s/%s", provider_name, capability_key,
                )
            else:
                caps[capability_key] = False
                logger.debug(
                    "no factory or class for %s/%s",
                    provider_name, capability_key,
                )

        self._capabilities[provider_name] = caps

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_chat(self, provider: str) -> Any:
        """获取聊天适配器实例。"""
        return self._get_module(provider, "chat")

    def get_token_count(self, provider: str) -> Any:
        """获取 token 统计器实例。"""
        return self._get_module(provider, "token_count")

    def get_module(self, provider: str, capability: str) -> Any:
        """获取任意 capability 模块。"""
        return self._get_module(provider, capability)

    def _get_module(self, provider: str, capability: str) -> Any:
        key = (provider, capability)
        if key not in self._modules:
            raise ModuleNotFoundError(
                f"provider '{provider}' has no module '{capability}' "
                f"(available: {list(self._capabilities.get(provider, {}))})"
            )
        return self._modules[key]

    def has_capability(self, provider: str, capability: str) -> bool:
        """检查 provider 是否具备某个能力。"""
        return self._capabilities.get(provider, {}).get(capability, False)

    def list_providers(self) -> list[str]:
        """列出所有已加载的 provider 名称。"""
        return list(self._provider_configs.keys())

    def list_models(self, provider: str) -> list[str]:
        """列出 provider 下的所有模型名。"""
        cfg = self._provider_configs.get(provider, {})
        return list(cfg.get("models", {}).keys())

    def get_provider_config(self, provider: str) -> dict[str, Any]:
        """获取 provider 的 model.json 内容。"""
        return self._provider_configs.get(provider, {})

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _load_config_json(self) -> dict[str, Any]:
        path = self._root / "config" / "config.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("config.json not found or invalid")
            return {}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _class_name_for_capability(
    provider: str, capability: str
) -> str:
    """根据 provider 名 + capability 推导类名。

    e.g. ("deepseek", "chat") → "DeepSeekChat"
    """
    return f"{provider.title()}{_snake_to_pascal(capability)}"


def _snake_to_pascal(name: str) -> str:
    return "".join(part.title() for part in name.split("_"))


def _find_class_in_module(
    mod, module_suffix: str, provider: str
) -> Any:
    """在模块中查找适配器类。

    匹配规则：
      1. 精确匹配推导名 e.g. DeepSeekChat
      2. 包含 capability 后缀 e.g. XxxChat
      3. 包含 provider 名（大小写不敏感）
    """
    target_suffix = _snake_to_pascal(module_suffix)
    provider_lower = provider.lower()

    for attr_name in dir(mod):
        obj = getattr(mod, attr_name)
        if not isinstance(obj, type):
            continue
        # 跳过私有类和错误类
        if attr_name.startswith("_") or "Error" in attr_name:
            continue

        name_lower = attr_name.lower()

        # 精确：类名以 provider 的 pascal 形式开头 + 后缀
        expected = _class_name_for_capability(provider, module_suffix)
        if attr_name == expected:
            return obj

        # 模糊：类名包含 capability 后缀 且包含 provider 名
        if target_suffix.lower() in name_lower and provider_lower in name_lower:
            return obj

    return None
