# Development history

This repository was published through GitHub's connected file/Git-data APIs. The
initial GitHub commits import the complete project source under GPL-3.0-only.

`history.bundle` preserves the original local Git repository, including the
individual feature commits and the transition from MIT to GPLv3. To inspect that
original history in a separate directory:

```sh
git clone history.bundle hand-control-original-history
git -C hand-control-original-history log --oneline
```

Continue normal development on this repository's `main` branch. The bundle is an
archive of the development history at publication time, not a generated model,
credential, user profile, or camera recording.
