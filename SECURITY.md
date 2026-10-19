# Security Policy

## Supported Versions

The latest 4.x helper for MoleditPy 5 receives security updates. Earlier major versions and historical releases are not maintained.

## Scope

The helper installs the unified MoleditPy package and creates launchers and file associations. Reports about executable/interpreter discovery, quoting paths and arguments, shortcut creation, downloaded dependencies, or per-user/system-wide registration are in scope. System-wide installation has the permissions of the account or elevation used to run it.

Use a Python environment and package source you trust. A launcher does not sandbox the application or its plugins. MoleditPy and standalone plugins have their own security policies; include the helper, application, OS and Python versions when reporting an issue. Do not include private paths, credentials or calculation data in a public report.

## Reporting a Vulnerability

**Please do not open a public issue for security vulnerabilities.**

To report a vulnerability, please contact the maintainers at titech.yoko.hiro[at]gmail.com.

Include the following in your report:

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- The version of the software affected
- Your operating system and environment details

If the issue is confirmed, a fix will be released as soon as possible.
