# 1688 Authenticated Automation Policy

- Scope: only after Jacken explicitly authorizes login automation for 1688.
- Credential handling: use credentials only inside a browser-based login flow; do not spray username/password across every crawler stack.
- Session model: maintain a separate authenticated site profile and separate run reports from anonymous mode.
- Allowed automation target: ordinary login and post-login browsing when the site accepts the session normally.
- Not allowed: bypassing slider, captcha, device-risk, punish, or other access-control challenges.
- Human-in-the-loop rule: if 1688 presents slider/captcha/device verification, pause and request manual completion in the browser session instead of attempting a bypass.
- Practical expectation: username/password may enable access to some content, but they do not guarantee unattended crawling success because 1688 frequently adds login-risk checks beyond credentials.
