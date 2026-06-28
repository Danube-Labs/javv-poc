// Conventional-commit linting for JAVV (AUDIT.md I12).
// release-please derives the SemVer bump + changelog from commit `type:`, so a malformed
// type silently mis-bumps or drops an entry — this guard fails the PR instead.
// Allowed types mirror development/standards/git-workflow.md exactly.
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [2, 'always', ['feat', 'fix', 'chore', 'docs', 'test', 'refactor']],
  },
};
