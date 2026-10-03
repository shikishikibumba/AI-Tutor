# Auth testing (admin only)
- Admin: admin@easa-study.app / Part66Admin!2026 (seeded from backend/.env on startup)
- POST /api/auth/login -> {token, user}; also sets httpOnly cookie access_token
- Send `Authorization: Bearer <token>` to /api/admin/* and /api/auth/me
- 5 failed logins per ip+email => 15 min lockout (429)
- Students do not log in; student endpoints are public
