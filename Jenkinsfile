// rad-shift's pipeline for Jenkins (roadmap item 35): the same checks as
// .github/workflows/ci.yml, as declarative stages, then a deploy of the
// packaged chart to a staging namespace on the local kind cluster.
//
// Runs on the local Jenkins (compose.jenkins.yaml, ci/jenkins/README.md).
// The job builds main only.

pipeline {
    // No agent for the pipeline as a whole: each stage asks for one, so
    // the wait for deploy approval doesn't hold a build executor.
    agent none

    options {
        timestamps()
        timeout(time: 45, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds()
    }

    environment {
        // Never report a CI run's errors to the real Sentry project.
        SENTRY_DSN = ''
        PIP_AUDIT = 'pip-audit==2.10.1'
    }

    stages {
        stage('CI') {
            agent { label 'python' }
            stages {
                stage('Build') {
                    // Python's build step: the locked environment, nothing resolved.
                    steps {
                        sh 'uv sync --locked'
                    }
                }

                stage('Lint') {
                    parallel {
                        stage('ruff') {
                            steps {
                                sh 'uv run ruff check . && uv run ruff format --check .'
                            }
                        }
                        stage('mypy') {
                            steps {
                                sh 'uv run mypy'
                            }
                        }
                    }
                }

                stage('Test') {
                    steps {
                        // The suite CI's parallel step runs (Docker-, helm- and
                        // Spark-backed tests have their own jobs there).
                        sh '''
                            mkdir -p reports
                            uv run pytest -q -n 8 -m "not perf and not kafka and not helm and not spark" \
                                --junitxml=reports/junit.xml \
                                --cov --cov-report=xml:reports/coverage.xml
                        '''
                    }
                    post {
                        always {
                            junit 'reports/junit.xml'
                            recordCoverage(tools: [[parser: 'COBERTURA', pattern: 'reports/coverage.xml']])
                        }
                    }
                }

                stage('Scan') {
                    parallel {
                        stage('bandit') {
                            steps {
                                sh 'uv run bandit -q -c pyproject.toml -r app scripts analytics'
                            }
                        }
                        stage('pip-audit') {
                            steps {
                                sh '''
                                    uv export --frozen --no-hashes --format requirements-txt --quiet > reports/requirements.txt
                                    uv tool run --quiet "$PIP_AUDIT" -r reports/requirements.txt --no-deps --disable-pip --progress-spinner off
                                '''
                            }
                        }
                    }
                }

                stage('Package') {
                    steps {
                        // The chart, versioned by build and stamped with the
                        // commit: the artifact the deploy stage promotes.
                        // (sh is dash here: no bash ${GIT_COMMIT:0:12}.)
                        sh '''
                            helm lint --strict deploy/helm/rad-shift
                            helm package deploy/helm/rad-shift --destination dist \
                                --version "0.1.0-build.${BUILD_NUMBER}" \
                                --app-version "$(echo "$GIT_COMMIT" | cut -c1-12)"
                        '''
                        archiveArtifacts artifacts: 'dist/rad-shift-*.tgz', fingerprint: true
                        stash name: 'chart', includes: 'dist/rad-shift-*.tgz'
                    }
                }
            }
            post {
                always {
                    cleanWs(deleteDirs: true, patterns: [[pattern: '.venv/**', type: 'INCLUDE']])
                }
            }
        }

        stage('Deploy to staging') {
            // Asked before an agent is taken (agent none above).
            input {
                message 'Deploy this build to the staging namespace on kind?'
                ok 'Deploy'
            }
            agent { label 'python' }
            environment {
                NAMESPACE = 'rad-shift-staging'
                RELEASE = 'rad-shift-staging'
            }
            steps {
                unstash 'chart'
                withCredentials([file(credentialsId: 'kind-kubeconfig', variable: 'KUBECONFIG')]) {
                    sh '''
                        kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
                        # Staging's own random secret, made once.
                        kubectl -n "$NAMESPACE" get secret rad-shift >/dev/null 2>&1 || \
                            kubectl -n "$NAMESPACE" create secret generic rad-shift \
                                --from-literal=DB_PASSWORD="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \\n')" \
                                --from-literal=JWT_SECRET="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \\n')"
                        # Small: one API pod, no Kafka, no ingress (production owns the hosts).
                        helm upgrade --install "$RELEASE" dist/rad-shift-*.tgz --namespace "$NAMESPACE" \
                            --set backend.autoscaling.enabled=false --set backend.replicas=1 \
                            --set worker.enabled=false --set kafka.enabled=false \
                            --set ingress.enabled=false \
                            --wait --timeout 10m --atomic
                        # Smoke test: the API answers and reaches its database.
                        kubectl -n "$NAMESPACE" exec "deploy/$RELEASE-backend" -c api -- \
                            python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:5000/health').read().decode())"
                    '''
                }
            }
        }
    }
}
