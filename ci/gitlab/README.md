# GitLab CI: the same pipeline in `.gitlab-ci.yml`

Roadmap item 37. The repository's pipeline is written in GitLab CI syntax (`.gitlab-ci.yml` at
the root). It runs **locally with [gitlab-ci-local](https://github.com/firecow/gitlab-ci-local)**,
for free: each job runs in its own Docker container, as GitLab's Docker executor would. There's
no GitLab account and no copy of the private code on gitlab.com. Mirroring the repository there
would publish it to a third party, and its free tier has 400 compute minutes a month.

```sh
npm install -g --min-release-age=14 gitlab-ci-local@4.77.1
gitlab-ci-local --list                     # parse and validate against GitLab's JSON schema
ci/gitlab/setup.sh                         # KUBECONFIG for the deploy job (gitignored)
gitlab-ci-local --network kind --variables-file ci/gitlab/variables.yml --manual deploy-staging
```

## The pipeline

| Stage | Jobs | GitLab features used |
|---|---|---|
| build | `build` | the only job that writes the uv cache (`cache: key: files: [uv.lock]`, `policy: pull-push`); the rest only pull |
| test | `lint`, `test` | `needs:` turns stages into a DAG, so jobs start when their needs finish; `artifacts: reports: junit` and `coverage_report` (Cobertura) feed the merge-request widgets; `coverage:` regex for the badge |
| scan | `bandit`, `pip-audit` | `extends: .python`, a hidden job used as a template |
| package | `package` | the Helm chart, versioned per pipeline (`CI_PIPELINE_IID`) and stamped with `CI_COMMIT_SHORT_SHA`, kept as an artifact |
| deploy | `deploy-staging` | `rules:` (default branch only) with `when: manual` (a play button); `environment: staging`; `KUBECONFIG` as a **file-type variable** |

All images are pinned by digest, and helm is checksum-verified. The deploy job upgrades the same
`rad-shift-staging` release the Jenkins pipeline installs: in the drill, Jenkins made revision 1
and GitLab revision 2.

## Drill (2026-11-25)

- **First run:** the job image tag `0.13.9-python3.12-bookworm-slim` doesn't exist.
  `docker buildx imagetools inspect` had printed a digest for it anyway, and I pinned that
  without pulling it. The pin is now taken from an actual pull (`trixie-slim`).
- **Second run:** a real bug in an existing test. The open-core export test fixture called
  `shutil.which("git")` without checking for `None`. GitHub's runners and the Jenkins agent have
  git, so it had never shown up. GitLab job images often don't: the runner fetches the code
  itself. The fixture now skips without git, like its neighbours do without trufflehog.
- **Third run:** all 7 jobs passed in 4 min 52 s (tests: 3,343 passed), and the manual deploy
  reached staging.
- **Note:** this pipeline doesn't run the Docker-backed tests (Kafka, Spark), so its coverage
  (95.1%) sits just above the 95% floor. GitHub CI appends those steps and reaches 97%.

## GitLab vs GitHub Actions vs Jenkins (interview points)

- **Structure:**
  - GitLab: stages plus `needs` (a DAG).
  - Actions: jobs plus `needs`.
  - Jenkins: stages in Groovy.
- **Reuse:**
  - GitLab: `extends`, `include:` (templates, other projects), and YAML anchors.
  - Actions: reusable workflows and composite actions.
  - Jenkins: shared libraries.
- **Runners:**
  - GitLab: shared runners on gitlab.com, or self-hosted with Docker, Kubernetes or shell
    executors.
  - Actions: hosted or self-hosted runners.
  - Jenkins: agents.
- **Secrets:**
  - GitLab: masked and protected CI/CD variables, protected environments and branches, and file
    variables.
  - Actions: environment secrets with required reviewers.
- **Built-in reports:** GitLab reads JUnit and coverage reports into merge requests natively.
  Actions needs a third-party action for the same thing.
- **Deploy gates:**
  - GitLab: `when: manual` plus protected environments.
  - Actions: environments with required reviewers.
  - Jenkins: `input`.
