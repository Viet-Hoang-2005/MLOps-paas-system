# Identity and tenancy

- JWTs are verified through current keys/JWKS, claims, expiry, issuer/audience configuration, and tenant binding.
- Browser refresh must reject inactive or deleted accounts and invalid user/tenant bindings before minting any tokens; the account check and issuance run under one transaction with the user row locked.
- With refresh rotation and blacklisting enabled, token consumption must succeed exactly once: check that the blacklist insertion created a record, and commit consumption and new outstanding token together. A concurrent revocation must prevent refresh from issuing a replacement.
- Inference only accepts access JWTs (`token_type=access`), never refresh tokens. Require `exp`, `iat`, `jti`, `user_id`, `tenant_id`, `token_type`, `iss`, `aud`, with issuer `django-control-plane` and audience `mlops-paas`.
- OAuth establishes identity; provider profile data is imported only under the intended first-login rules.
- GitHub account linking uses only a primary and verified address from the authenticated email API, including paginated results; never trust the profile email as proof of ownership and never fall back on provider failure.
- API keys store a prefix and hash/digest, support revocation, and are project/tenant scoped.
- Public access mode never bypasses project/version existence and routing validation.

## API invariants

- Public APIs expose UUIDs only.
- Every tenant-owned query filters by authenticated tenant/owner before returning existence.
- Cross-tenant resources normally return 404 to avoid enumeration.
- Serializer validation does not replace ownership filtering in selectors/services.
- Inference paths bind tenant, project, and version consistently.

Test valid, missing, revoked, expired, invalid-signature, wrong-tenant, and cross-project cases.

Account avatars use a single CustomUser.avatar reference and server-generated immutable keys under users/{tenant_id}/avatar/. All writes act on the authenticated account (OAuth import only for account creation). Validate uploads as images up to 5 MiB; reject raw storage-key/URL assignment and upload+remove ambiguity. Object cleanup must validate tenant scope and skip any currently referenced key, including after concurrent replacements.
