# Pull Request Checklist

## Summary

Describe what changed and why.

## Type of change

- [ ] Refactor / foundation work
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Tests
- [ ] CI / deployment

## Safety checks

- [ ] Changes are on a branch, not directly on `main`
- [ ] No real customer/order files committed
- [ ] No secrets or credentials committed
- [ ] Core business logic changes have tests
- [ ] Streamlit app was tested manually

## Test results

Paste test output or summarize:

```text
python -m pytest
python -m compileall .


For `README.md`, don’t replace the whole thing right now. To avoid another paste mess, just add this section near the bottom before **Future Improvements**:

```markdown
---

# Local Development

Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1