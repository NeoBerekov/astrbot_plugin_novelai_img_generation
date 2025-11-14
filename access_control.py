"""白名单与每日限额管理。"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Optional


@dataclass
class UserQuota:
    qq: str
    daily_limit: int
    remaining: int
    last_reset: str  # ISO 时间戳字符串，例如 "2025-01-15T12:30:45.123456"
    last_used_at: Optional[str] = None
    nickname: Optional[str] = None
    identity_groups: Optional[list[str]] = None
    refresh_interval_minutes: Optional[int] = None  # 刷新间隔（分钟），None 表示使用默认的每日刷新

    def to_dict(self) -> Dict[str, object]:
        return {
            "daily_limit": self.daily_limit,
            "remaining": self.remaining,
            "last_reset": self.last_reset,
            "last_used_at": self.last_used_at,
            "nickname": self.nickname,
            "identity_groups": self.identity_groups,
            "refresh_interval_minutes": self.refresh_interval_minutes,
        }


class AccessControl:
    """对白名单、限额及每日使用做管理。"""

    def __init__(self, storage_path: str, default_daily_limit: int = 10) -> None:
        self.storage_path = storage_path
        self.default_daily_limit = default_daily_limit
        self._lock = asyncio.Lock()
        self._data: Dict[str, Dict[str, object]] = {"users": {}, "groups": {}, "admin": {}}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.storage_path):
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            self._save_locked()
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except json.JSONDecodeError:
            self._data = {"users": {}, "groups": {}}
        self._data.setdefault("users", {})
        self._data.setdefault("groups", {})
        self._data.setdefault("admin", {})

    def _save_locked(self) -> None:
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _today(self) -> str:
        return date.today().isoformat()

    def _now(self) -> str:
        """返回当前时间的 ISO 时间戳字符串。"""
        return datetime.now().isoformat()

    def _get_user(self, qq: str) -> Optional[UserQuota]:
        user = self._data.get("users", {}).get(qq)
        if not user:
            return None
        # 兼容旧数据：如果 last_reset 是日期格式（只有日期，没有时间），转换为时间戳
        last_reset = user.get("last_reset", "")
        if last_reset and "T" not in last_reset:
            # 旧格式：只有日期，转换为当天的开始时间戳
            try:
                reset_date = datetime.fromisoformat(last_reset).date()
                last_reset = datetime.combine(reset_date, datetime.min.time()).isoformat()
            except (ValueError, AttributeError):
                # 如果解析失败，使用当前时间
                last_reset = self._now()
        user_data = user.copy()
        user_data["last_reset"] = last_reset
        return UserQuota(qq=qq, **user_data)

    def _set_user(self, user: UserQuota) -> None:
        self._data.setdefault("users", {})[user.qq] = user.to_dict()

    def _auto_reset_user(self, user: UserQuota) -> UserQuota:
        """根据刷新间隔自动重置用户的使用次数。"""
        now = datetime.now()
        
        # 解析 last_reset 时间戳
        try:
            if "T" in user.last_reset:
                last_reset_time = datetime.fromisoformat(user.last_reset)
            else:
                # 兼容旧格式：只有日期
                reset_date = datetime.fromisoformat(user.last_reset).date()
                last_reset_time = datetime.combine(reset_date, datetime.min.time())
        except (ValueError, AttributeError):
            # 如果解析失败，重置为当前时间
            last_reset_time = now
            user.last_reset = now.isoformat()

        # 计算时间差（分钟）
        time_diff_minutes = (now - last_reset_time).total_seconds() / 60

        # 确定刷新间隔
        refresh_interval = user.refresh_interval_minutes
        if refresh_interval is None:
            # 默认：每日刷新（1440分钟）
            refresh_interval = 1440

        # 如果时间差超过刷新间隔，重置使用次数
        if time_diff_minutes >= refresh_interval:
            user.last_reset = now.isoformat()
            user.remaining = user.daily_limit

        return user

    async def check_permission(self, qq: str) -> bool:
        async with self._lock:
            return qq in self._data.get("users", {})

    async def check_group_permission(self, group_id: str) -> bool:
        async with self._lock:
            return group_id in self._data.get("groups", {})

    async def add_to_whitelist(
        self,
        qq: str,
        limit: Optional[int] = None,
        nickname: Optional[str] = None,
        identity_groups: Optional[list[str]] = None,
    ) -> UserQuota:
        async with self._lock:
            daily_limit = limit or self.default_daily_limit
            user = UserQuota(
                qq=qq,
                daily_limit=daily_limit,
                remaining=daily_limit,
                last_reset=self._now(),
                nickname=nickname,
                identity_groups=identity_groups,
            )
            self._set_user(user)
            self._save_locked()
            return user

    async def record_admin(self, admin_id: str, nickname: Optional[str] = None) -> None:
        async with self._lock:
            admin_entry = self._data.setdefault("admin", {})
            admin_entry[str(admin_id)] = {"昵称": nickname or ""}
            self._save_locked()

    async def remove_from_whitelist(self, qq: str) -> bool:
        async with self._lock:
            users = self._data.get("users", {})
            if qq in users:
                users.pop(qq)
                self._save_locked()
                return True
            return False

    async def add_group(self, group_id: str, name: Optional[str] = None) -> Dict[str, object]:
        async with self._lock:
            group_entry = {"name": name}
            self._data.setdefault("groups", {})[group_id] = group_entry
            self._save_locked()
            return group_entry

    async def remove_group(self, group_id: str) -> bool:
        async with self._lock:
            groups = self._data.get("groups", {})
            if group_id in groups:
                groups.pop(group_id)
                self._save_locked()
                return True
            return False

    async def get_group_info(self, group_id: str) -> Optional[Dict[str, object]]:
        async with self._lock:
            groups = self._data.get("groups", {})
            return groups.get(group_id)

    async def set_quota(
        self,
        qq: str,
        limit: int,
        nickname: Optional[str] = None,
        identity_groups: Optional[list[str]] = None,
        refresh_interval_minutes: Optional[int] = None,
    ) -> UserQuota:
        if limit <= 0:
            raise ValueError("每日限额必须大于0")
        async with self._lock:
            user = self._get_user(qq)
            if not user:
                user = UserQuota(
                    qq=qq,
                    daily_limit=limit,
                    remaining=limit,
                    last_reset=self._now(),
                    nickname=nickname,
                    identity_groups=identity_groups,
                    refresh_interval_minutes=refresh_interval_minutes,
                )
            else:
                user.daily_limit = limit
                user.remaining = min(user.remaining, limit)
                if nickname:
                    user.nickname = nickname
                if identity_groups is not None:
                    user.identity_groups = identity_groups
                if refresh_interval_minutes is not None:
                    user.refresh_interval_minutes = refresh_interval_minutes
            self._set_user(user)
            self._save_locked()
            return user

    async def check_quota(self, qq: str) -> bool:
        async with self._lock:
            user = self._get_user(qq)
            if not user:
                return False
            user = self._auto_reset_user(user)
            self._set_user(user)
            self._save_locked()
            return user.remaining > 0

    async def consume_quota(self, qq: str) -> None:
        async with self._lock:
            user = self._get_user(qq)
            if not user:
                raise ValueError("用户不在白名单")
            user = self._auto_reset_user(user)
            if user.remaining <= 0:
                raise ValueError("用户已达到每日限额")
            user.remaining -= 1
            user.last_used_at = datetime.now().isoformat()
            self._set_user(user)
            self._save_locked()

    async def reset_daily_quota(self) -> None:
        async with self._lock:
            for qq, info in list(self._data.get("users", {}).items()):
                user = UserQuota(qq=qq, **info)
                user = self._auto_reset_user(user)
                self._set_user(user)
            self._save_locked()

    async def get_user_info(self, qq: str) -> Optional[Dict[str, object]]:
        async with self._lock:
            user = self._get_user(qq)
            if not user:
                return None
            user = self._auto_reset_user(user)
            self._set_user(user)
            self._save_locked()
            data = user.to_dict().copy()
            data["qq"] = qq
            return data
