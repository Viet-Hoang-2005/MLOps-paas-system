# Identity and tenancy

- JWTs are verified through current keys/JWKS, claims, expiry, issuer/audience configuration, and tenant binding.
- OAuth establishes identity; provider profile data is imported only under the intended first-login rules.
- API keys store a prefix and hash/digest, support revocation, and are project/tenant scoped.
- Public access mode never bypasses project/version existence and routing validation.

## API invariants

- Public APIs expose UUIDs only.
- Every tenant-owned query filters by authenticated tenant/owner before returning existence.
- Cross-tenant resources normally return 404 to avoid enumeration.
- Serializer validation does not replace ownership filtering in selectors/services.
- Inference paths bind tenant, project, and version consistently.

Test valid, missing, revoked, expired, invalid-signature, wrong-tenant, and cross-project cases.
