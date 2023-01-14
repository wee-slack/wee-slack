from __future__ import annotations

import weechat


class Proxy:
    @property
    def name(self):
        return weechat.config_string(weechat.config_get("weechat.network.proxy_curl"))

    @property
    def enabled(self):
        return bool(self.type)

    @property
    def _proxy_option_prefix(self):
        return f"weechat.proxy.{self.name}"

    @property
    def type(self):
        return weechat.config_string(
            weechat.config_get(f"{self._proxy_option_prefix}.type")
        )

    @property
    def address(self):
        return weechat.config_string(
            weechat.config_get(f"{self._proxy_option_prefix}.address")
        )

    @property
    def port(self):
        return weechat.config_integer(
            weechat.config_get(f"{self._proxy_option_prefix}.port")
        )

    @property
    def ipv6(self):
        return weechat.config_boolean(
            weechat.config_get(f"{self._proxy_option_prefix}.ipv6")
        )

    @property
    def username(self):
        return weechat.config_string(
            weechat.config_get(f"{self._proxy_option_prefix}.username")
        )

    @property
    def password(self):
        return weechat.config_string(
            weechat.config_get(f"{self._proxy_option_prefix}.password")
        )

    @property
    def curl_option(self):
        if not self.enabled:
            return ""

        user = (
            f"{self.username}:{self.password}@"
            if self.username and self.password
            else ""
        )
        return f"-x{self.type}://{user}{self.address}:{self.port}"
