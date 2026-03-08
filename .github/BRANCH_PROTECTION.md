# Branch Protection Setup

Configure these rules manually in GitHub Settings > Branches > Branch protection rules.

## Rule: `main`

- [x] Require a pull request before merging
  - [x] Require approvals: 1
  - [x] Dismiss stale pull request approvals when new commits are pushed
- [x] Require status checks to pass before merging (enable once CI is set up)
- [x] Require branches to be up to date before merging
- [x] Require conversation resolution before merging
- [ ] Require signed commits (optional)
- [x] Do not allow bypassing the above settings

## Branch Naming Convention

- `feature/<short-description>` — new features
- `fix/<short-description>` — bug fixes
- `refactor/<short-description>` — code refactoring
- `docs/<short-description>` — documentation only
- `spike/<short-description>` — experimental prototypes
