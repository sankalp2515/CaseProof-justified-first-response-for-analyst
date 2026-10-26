"""Server-mapped staff roles and exact service identities; headers cannot choose a role."""

from google.auth.transport.requests import Request
from google.oauth2 import id_token

from caseproof.domain.contracts import Actor


def claims(authorization, audience):
    if not audience or not authorization or not authorization.startswith("Bearer "):
        raise PermissionError("authenticated_identity_required")
    try:
        return id_token.verify_oauth2_token(authorization[7:], Request(), audience=audience)
    except Exception:
        raise PermissionError("authenticated_identity_required") from None


def staff(settings, authorization):
    token = claims(authorization, settings.cloud_staff_audience)
    if token.get("email_verified") is not True:
        raise PermissionError("verified_staff_identity_required")
    assigned = settings.cloud_staff_principals.get(token.get("sub", ""))
    if not assigned:
        raise PermissionError("staff_identity_not_assigned")
    return Actor(user_id=token["sub"], role=assigned["role"], tenant_id=assigned["tenant_id"])


def service(settings, authorization, expected):
    token = claims(authorization, settings.cloud_worker_url)
    if not expected or token.get("email_verified") is not True or token.get("email") != expected:
        raise PermissionError("service_identity_required")
    return token
