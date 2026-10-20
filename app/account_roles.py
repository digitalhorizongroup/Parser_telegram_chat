import json
import os
from pathlib import Path


class AccountRoles:
    ROLES = {"parser", "outreach", "autoresponder", "reserve"}

    def __init__(self, path: Path):
        self.path = Path(path)

    def _read(self) -> dict[str, str]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return {}
        return {str(name): role for name, role in value.items() if role in self.ROLES} if isinstance(value, dict) else {}

    def get(self, account: str) -> str:
        return self._read().get(str(account), "parser")

    def set(self, account: str, role: str) -> str:
        if role not in self.ROLES:
            raise ValueError("Неизвестное назначение аккаунта")
        values = self._read()
        values[str(account)] = role
        self._write(values)
        return role

    def delete(self, account: str):
        values = self._read()
        if str(account) in values:
            values.pop(str(account))
            self._write(values)

    def _write(self, values: dict[str, str]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)
