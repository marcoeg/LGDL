class PolicyGuard:
    def __init__(self, allowlist=None):
        self.allowlist = set(allowlist or [])

    def allowed(self, capability_name: str) -> bool:
        return capability_name in self.allowlist
