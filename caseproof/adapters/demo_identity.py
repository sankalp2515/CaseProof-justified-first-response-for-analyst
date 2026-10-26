from caseproof.domain.contracts import Actor

USERS = {
    "analyst": Actor(user_id="demo-analyst", role="analyst", tenant_id="demo"),
    "reviewer": Actor(user_id="demo-reviewer", role="reviewer", tenant_id="demo"),
    "admin": Actor(user_id="demo-admin", role="admin", tenant_id="demo"),
}


class DemoIdentity:
    def actor(self, user_id):
        if user_id not in USERS:
            raise PermissionError("unknown demo identity")
        return USERS[user_id]
